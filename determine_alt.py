import eti
import configobj
import DbConn
import datetime
import pytz
import random

import numpy
import scipy
import scipy.stats
from sklearn import linear_model
from sklearn import svm

with open('alts.csv', 'r') as alt_file:
  alts = []
  for line in alt_file:
    alts.append([int(x) for x in line.strip().split(',')])

random.shuffle(alts)
test_set = alts[:len(alts)/2]
train_set = alts[len(alts)/2:]

alt_to_main = {x[0]: x[1] for x in alts}

# filters out all users with fewer posts than this.
min_user_posts = 5000

# restricts the "if this alt is this user's, how much did the posting disrupt normal levels" analysis
alt_started_window_radius = datetime.timedelta(weeks=4)

def dict_dot(a, b):
  return sum(a[key] * b[key] for key in a if key in b)

def dict_corr(a, b):
  keys = list(a.viewkeys() | b.viewkeys())
  return numpy.corrcoef(
      [a.get(x, 0) for x in keys],
      [b.get(x, 0) for x in keys])[0, 1]

config = configobj.ConfigObj(infile=open('/home/shaldengeki/llAnimuBot/config.txt', 'r'))
db = DbConn.DbConn(username=config['DB']['llBackup']['username'], password=config['DB']['llBackup']['password'], database=config['DB']['llBackup']['name'])

# assemble a list of topics.
sat_db = DbConn.DbConn(username=config['DB']['llAnimu']['username'], password=config['DB']['llAnimu']['password'], database=config['DB']['llAnimu']['name'])
sats = [eti.Topic(db, topic_id).load() for topic_id in sat_db.table('sats').fields('ll_topicid').where(completed=1).order('ll_topicid ASC').list(valField='ll_topicid')]

# assemble a dict of all users and their post counts in each SAT.
users = {}
for sat in sats:
  sat_post_counts = sat.users
  for post_count in sat_post_counts:
    if post_count['user'].id not in users:
      users[post_count['user'].id] = {'user': post_count['user'].load(), 'posts': {sat.id: post_count['posts']}}
    else:
      users[post_count['user'].id]['posts'][sat.id] = post_count['posts']

for user_id in users:
  users[user_id]['total_posts'] = sum(users[user_id]['posts'][topic_id] for topic_id in users[user_id]['posts'])

filtered_users = [user_id for user_id in users if users[user_id]['total_posts'] >= min_user_posts]

# construct day-by-day and week-by-week post counts for each user.
user_daily_posts = {}
for user_id in users:
  posts = db.table('posts').fields("FROM_UNIXTIME(date, '%%Y-%%m-%%d') AS new_date", "COUNT(*) AS count").where(userid=user_id).group('new_date').order('new_date ASC').dict(keyField='new_date', valField='count')
  user_daily_posts[user_id] = sorted([(datetime.datetime.strptime(time_string, '%Y-%m-%d').date(), posts[time_string]) for time_string in posts], key=lambda x: x[0])

user_weekly_posts = {}
for user_id in users:
  posts = db.table('posts').fields("FROM_UNIXTIME(date, '%%Y-%%U') AS new_date", "COUNT(*) AS count").where(userid=user_id).group('new_date').order('new_date ASC').dict(keyField='new_date', valField='count')
  user_weekly_posts[user_id] = sorted([(datetime.datetime.strptime(time_string + '-0', '%Y-%U-%w').date(), posts[time_string]) for time_string in posts], key=lambda x: x[0])

for alt_id in alts:
  alt_dates = {daily_tuple[0]: daily_tuple[1] for daily_tuple in user_weekly_posts[alt_id]}
  alt_started = min(alt_dates.keys())

  alt_similarities = []
  for user_id in filtered_users:
    # for each user, get this user's mean activity right up to the point that the alt started posting.
    user_similarities = [user_id]
    user_priors = []
    user_posteriors = []
    user_coincide_posteriors = []
    for post_tuple in user_weekly_posts[user_id]:
      if post_tuple[0] < alt_started:
        # this is prior to the alt starting posting.
        # restrict this analysis to N months on either side of alt_started.
        if alt_started - post_tuple[0] < alt_started_window_radius:
          user_priors.append(post_tuple[1])
      else:
        # this is after the alt started posting.
        if post_tuple[0] in alt_dates:
          user_coincide_posteriors.append((post_tuple[1], alt_dates[post_tuple[0]]))
          if post_tuple[0] - alt_started < alt_started_window_radius:
          # only append this to the posteriors if it's within the window radius.
            total_sum = post_tuple[1] + alt_dates[post_tuple[0]]
            user_posteriors.append(total_sum)
    if len(user_priors) < 2 or not user_posteriors:
      # user started posting after this alt. skip them.
      # print "User ID",user_id,"has less than two posts on at least one side of this window. Skipping."
      continue
    user_prior_mean = float(sum(user_priors)) / len(user_priors)
    user_prior_stdev = numpy.std(user_priors)
    # user_posterior_stdev = numpy.std(user_posteriors)
    user_posterior_mean = float(sum(user_posteriors)) / len(user_posteriors)
    user_posterior_change = user_posterior_mean - user_prior_mean
    user_posterior_change_normed = user_posterior_change / user_prior_stdev
    # user_posterior_change_normed_alt = user_posterior_change / user_posterior_stdev
    user_similarities.extend([user_posterior_change,user_posterior_change_normed])
    # now find correlation between these two users' post vectors.
    user_correlation = scipy.stats.pearsonr(*zip(*user_coincide_posteriors))[0]
    user_similarities.append(user_correlation)
    # finally, append this row of similarities.
    alt_similarities.append(user_similarities)

for user_id in users:
  # get time in UTC
  utc_dt = datetime.datetime.utcfromtimestamp(users[user_id]['user'].created).replace(tzinfo=pytz.utc)

  # convert it to tz
  tz = pytz.timezone('America/Chicago')
  user_created = tz.normalize(utc_dt.astimezone(tz))

  # get post history up to this point, segmented by day.
  