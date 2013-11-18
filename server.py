#!/usr/bin/env python
"""
  Unofficial ETI API server.
  Uses Flask and MySQLdb.
  Written by shaldengeki <shaldengeki@gmail.com>
  Released under WTFPL <http://www.wtfpl.net/txt/copying>
"""

from flask import Flask, request, jsonify, g, redirect, url_for, abort, render_template, flash
import flask_login
import functools
import urllib2
import urllib
import sys, os
import traceback

import DbConn
from eti import InvalidTopicError, InvalidPostError, InvalidUserError, InvalidTagError, Topic, Post, User, TopicList, PostList, Tag

# database, secret token config
app = Flask(__name__)
DB_CREDENTIALS_FILE = "config.txt"
with open(DB_CREDENTIALS_FILE, 'r') as f:
  MYSQL_USERNAME,MYSQL_PASSWORD,MYSQL_DB = f.readline().strip().split(',')
  app.secret_key = f.readline().strip()
app.config.from_object(__name__)

# initialize flask-login
login_manager = flask_login.LoginManager()
login_manager.session_protection = "strong"
login_manager.init_app(app)

# flask user functions.
@login_manager.user_loader
def load_user(userid):
  try:
    return User(DbConn.DbConn(app.config['MYSQL_USERNAME'], app.config['MYSQL_PASSWORD'], app.config['MYSQL_DB']), int(userid))
  except InvalidUserError, e:
    return None

def unauthorized():
  message = {'message': "Authentication is required to access this resource."}
  resp = jsonify(message)
  resp.status_code = 401
  return resp

@login_manager.unauthorized_handler
def unauthorized_handler():
  message = {'message': "Authentication is required to access this resource."}
  resp = jsonify(message)
  resp.status_code = 401
  return resp

def current_user_required(f):
  '''
    Decorator for functions that require the user to both 
      be logged-in, and 
      have the given userID.
  '''
  @functools.wraps(f)
  def decorated_function(*args, **kwargs):
    if not flask_login.current_user.is_authenticated() or int(flask_login.current_user.get_id()) != int(kwargs['userid']):
      return unauthorized()
    else:
      return flask_login.login_required(f)(*args, **kwargs)
  return decorated_function

# output response shorthand functions.
def jsonify_list(outputList, key):
  resp = jsonify({key: outputList})
  resp.status_code = 200
  return resp

def jsonify_object(outputObj):
  """
  Takes an object (or None) and returns a proper json response object.
  """
  status = 200
  if outputObj is None:
    status = 404
    outputObj = {}
  else:
    outputObj = outputObj.dict()
  resp = jsonify(outputObj)
  resp.status_code = status
  return resp

def eti_down():
  message = {'message': "ETI is down. Cannot authenticate you."}
  resp = jsonify(message)
  resp.status_code = 502
  return resp

def not_found():
  message = {'message': "The resource you requested could not be found."}
  resp = jsonify(message)
  resp.status_code = 404
  return resp

@app.before_request
def before_request():
  g.db = DbConn.DbConn(app.config['MYSQL_USERNAME'], app.config['MYSQL_PASSWORD'], app.config['MYSQL_DB'])

@app.teardown_request
def teardown_request(exception):
  try:
    g.db.close()
  except AttributeError, e:
    pass

@app.route('/topics')
def api_topics():
  """
  Topic listing. Request params: query, tag, start, limit
  """
  try:
    topicList = TopicList(g.db)
    query = request.args['query'] if 'query' in request.args else None
    if 'tag' in request.args:
      tagNames = request.args.getlist('tag')
      for name in tagNames:
        if name.startswith("-"):
          topicList.excludeTag(Tag(g.db, name[1:]))
        else:
          topicList.includeTag(Tag(g.db, name))
    if 'start' in request.args:
      requestedStart = int(request.args['start'])
      topicList.start(0 if requestedStart < 0 else requestedStart)
    if 'limit' in request.args:
      topicLimit = 1000 if int(request.args['limit']) > 1000 or int(request.args['limit']) < 1 else int(request.args['limit'])
      topicList.limit(topicLimit)
    searchTopics = [topic.dict() for topic in topicList.search(query=query, includes=['user', 'tags'])]
    return jsonify_list(searchTopics, 'topics')
  except InvalidTagError:
    return not_found()

@app.route('/topics/<int:topicid>')
def api_topic(topicid):
  """
  Display a single topic.
  """
  try:
    topicObj = Topic(g.db, topicid).load(includes=['user', 'tags'])
  except InvalidTopicError:
    return not_found()
  return jsonify_object(topicObj)

@app.route('/topics/<int:topicid>/posts')
def api_topic_posts(topicid):
  """
  Display a single topic's posts. Request params: user, limit, start
  """
  try:
    topicObj = Topic(g.db, topicid)
  except InvalidUserError:
    return not_found()
  postList = PostList(g.db).topic(topicObj)
  if 'user' in request.args:
    try:
      filterUser = User(g.db, int(request.args['user']))
    except InvalidUserError, e:
      return not_found()
    postList.user(filterUser)
  if 'limit' in request.args:
    requestedLimit = int(request.args['limit'])
    postList.limit(1000 if requestedLimit > 1000 or requestedLimit < 1 else requestedLimit)
  if 'start' in request.args:
    requestedStart = int(request.args['start'])
    postList.start(0 if requestedStart < 0 else requestedStart)
  searchPosts = [post.dict() for post in postList.search(includes=['user'])]
  return jsonify_list(searchPosts, 'posts')

@app.route('/topics/<int:topicid>/users')
def api_topic_users(topicid):
  """
  Display a single topic's users with post-counts.
  """
  try:
    users = [{'user': user['user'].load().dict(), 'posts': int(user['posts'])} for user in Topic(g.db, topicid).users]
  except InvalidTopicError:
    return not_found()
  return jsonify_list(users, 'users')

@app.route('/posts')
def api_posts():
  """
  Display all posts. Not yet implemented.
  """
  return 'List of ' + url_for('api_posts')

@app.route('/posts/<int:postid>')
def api_post(postid):
  """
  Display a single post.
  """
  try:
    postObj = Post(g.db, postid).load(includes=['user', 'topic'])
    postObj.topic = postObj.topic.dict()
  except InvalidPostError:
    return not_found()
  return jsonify_object(postObj)

@app.route('/users')
def api_users():
  """
  Listing of all users. Not yet implemented.
  """
  return 'List of ' + url_for('api_users')

@app.route('/users/<int:userid>')
def api_user(userid):
  """
  Display a single user.
  """
  try:
    userObj = User(g.db, userid).load()
  except InvalidUserError:
    return not_found()
  return jsonify_object(userObj)

@app.route('/users/<int:userid>/posts')
@current_user_required
def api_user_posts(userid):
  """
  Display a single user's posts. Requires authentication. Request params: topic, limit, start
  """
  try:
    userObj = User(g.db, userid)
  except InvalidUserError:
    return not_found()
  postList = PostList(g.db)
  postList.db.where(('posts.userid=%s', userObj.id))
  if 'topic' in request.args:
    try:
      filterTopic = Topic(g.db, int(request.args['topic']))
    except InvalidUserError, e:
      return not_found()
    postList.topic(filterTopic)
  if 'limit' in request.args:
    requestedLimit = int(request.args['limit'])
    postList.limit(1000 if requestedLimit > 1000 or requestedLimit < 1 else requestedLimit)
  if 'start' in request.args:
    requestedStart = int(request.args['start'])
    postList.start(0 if requestedStart < 0 else requestedStart)
  searchPosts = [post.dict() for post in postList.search(includes=['topic', 'user'])]
  return jsonify_list(searchPosts, 'posts')

@app.route('/users/<int:userid>/topics')
@current_user_required
def api_user_topics(userid):
  """
  Display a single user's topics. Requires authentication. Request params: query, tag, limit, start
  """
  try:
    userObj = User(g.db, userid)
  except InvalidUserError:
    return not_found()
  try:
    topicList = TopicList(g.db).user(userObj)
    query = request.args['query'] if 'query' in request.args else None
    if 'tag' in request.args:
      tagNames = request.args.getlist('tag')
      for name in tagNames:
        if name.startswith("-"):
          topicList.excludeTag(Tag(g.db, name[1:]))
        else:
          topicList.includeTag(Tag(g.db, name))
    if 'limit' in request.args:
      requestedLimit = int(request.args['limit'])
      topicList.limit(1000 if requestedLimit > 1000 or requestedLimit < 1 else requestedLimit)
    if 'start' in request.args:
      requestedStart = int(request.args['start'])
      topicList.start(0 if requestedStart < 0 else requestedStart)
    searchTopics = [post.dict() for post in topicList.search(query=query, includes=['user', 'tags'])]
  except InvalidTagError:
    return not_found()
  return jsonify_list(searchTopics, 'topics')

@app.route('/tags')
def api_tags():
  """
  Listing of all tags. Not yet implemented.
  """
  return 'List of ' + url_for('api_tags')

@app.route('/tags/<title>')
def api_tag(title):
  """
  Display a single tag.
  """
  try:
    tagObj = Tag(g.db, title).load()
  except InvalidTagError:
    return not_found()
  return jsonify_object(tagObj)

@app.route('/tags/<title>/topics')
def api_tag_topics(title):
  """
  Display a single tag's topics. Request params: query, limit, start
  """
  try:
    tagObj = Tag(g.db, title).load()
  except InvalidTagError:
    return not_found()
  topicList = TopicList(g.db).tags([tagObj])
  query = request.args['query'] if 'query' in request.args else None
  if 'limit' in request.args:
    requestedLimit = int(request.args['limit'])
    topicList.limit(1000 if requestedLimit > 1000 or requestedLimit < 1 else requestedLimit)
  if 'start' in request.args:
    requestedStart = int(request.args['start'])
    topicList.start(0 if requestedStart < 0 else requestedStart)
  searchTopics = [topic.dict() for topic in topicList.search(query=query, includes=['user', 'tags'])]
  return jsonify_list(searchTopics, 'topics')

@app.route('/login')
def api_login():
  """
  Authenticate as a user. Request params: username
  """
  if 'user' not in request.args:
    return unauthorized()
  # hit the ETI auth api.
  authParams = urllib.urlencode({'username': request.args['user'], 'ip': request.remote_addr})
  try:
    checkAuth = urllib2.urlopen('https://boards.endoftheinter.net/scripts/login.php?' + authParams).read()
  except (urllib2.URLError, urllib2.HTTPError) as e:
    return eti_down()
  if checkAuth == '0':
    return unauthorized()
  else:
    userID = int(g.db.table("user_names").fields("user_id").where(name=request.args['user']).firstValue())
    if not userID:
      return unauthorized()
    flask_login.login_user(User(g.db, userID))
    return redirect(request.args.get("next") or url_for('api_root'))

@app.route('/logout')
@flask_login.login_required
def api_logout():
  """
  Clear authentication.
  """
  flask_login.logout_user()
  return redirect(url_for('api_root'))

@app.route('/')
def api_root():
  """Sitemap"""
  func_list = {}
  for rule in app.url_map.iter_rules():
    if rule.endpoint != 'static':
      func_list[rule.rule] = app.view_functions[rule.endpoint].__doc__
  return jsonify(func_list)
if __name__ == '__main__':
  app.run(port=16723, debug=True)
