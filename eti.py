#!/usr/bin/env python
"""
  Topic and post classes for ETI unofficial API.
  Uses Flask, MySQLdb, and pytz.
  Written by shaldengeki <shaldengeki@gmail.com>
  Released under WTFPL <http://www.wtfpl.net/txt/copying>
"""

import collections
import json
import pytz

class InvalidTopicError(Exception):
  def __init__(self, topic):
    super(InvalidTopicError, self).__init__()
    self.topic = topic
  def __str__(self):
    return "\n".join([
      super(InvalidTopicError, self).__str__(),
      "TopicID: " + unicode(self.topic.id)
      ])

class InvalidUserError(Exception):
  def __init__(self, topic):
    super(InvalidUserError, self).__init__()
    self.user = user
  def __str__(self):
    return "\n".join([
      super(InvalidUserError, self).__str__(),
      "UserID: " + unicode(self.user.id)
      ])

class ArchivedTopicError(InvalidTopicError):
  def __str__(self):
    return "\n".join([
      super(ArchivedTopicError, self).__str__(),
      "Archived: " + unicode(self.topic._archived)
      ])

class InvalidPostError(InvalidTopicError):
  def __init__(self, post):
    super(InvalidPostError, self).__init__(post.topic)
    self.post = post
  def __str__(self):
    return "\n".join([
      super(InvalidPostError, self).__str__(),
      "PostID: " + unicode(self.post.id),
      ])

class MalformedPostError(InvalidPostError):
  def __init__(self, post, topic, text):
    super(MalformedPostError, self).__init__(post, topic)
    self.text = text
  def __str__(self):
    return "\n".join([
        super(MalformedPostError, self).__str__(),
        "Text: " + unicode(self.text)
      ])

class InvalidTagError(Exception):
  def __init__(self, tag):
    super(InvalidTagError, self).__init__()
    self.tag = tag
  def __str__(self):
    return "\n".join([
      super(InvalidTagError, self).__str__(),
      "Tag Title: " + unicode(self.tag.title)
      ])

class BaseObject(object):
  '''
  Base object with common features.
  '''
  def __str__(self):
    return str(self.dict())

  def dict(self):
    """
    Filters out all non-serializable attributes of this object.
    """
    resultDict = {}
    for k,v in self.__dict__.iteritems():
      if isinstance(v, BaseObject):
        v = v.dict()
      elif k == 'db' or k.startswith('_'):
        continue
      resultDict[k] = v
    return resultDict

  def set(self, attrDict):
    """
    Sets attributes of this post object with keys found in dict.
    """
    for key in attrDict:
      setattr(self, key, attrDict[key])
    return self


class Post(BaseObject):
  '''
  Post-loading object for ETI unofficial API.
  '''
  def __init__(self, db, id):
    self.db = db
    self.id = id
    if not isinstance(self.id, int) or int(self.id) < 1:
      raise InvalidPostError(self)
    else:
      self.id = int(self.id)
    self._page = None

  def __contains__(self, searchString):
    return searchString in self.html

  def __index__(self):
    return self.id

  def __hash__(self):
    return self.id

  def __eq__(self, post):
    return self.id == post.id

  def load(self):
    """
    Fetches post info.
    """
    dbPost = self.db.table("posts").fields("*").where(ll_messageid=self.id).firstRow()
    if not dbPost:
      raise InvalidPostError(self)
    postInfo = {
      'id': int(dbPost['ll_messageid']),
      'topic': Topic(self.db, int(dbPost['ll_topicid'])),
      'user': User(self.db, int(dbPost['userid'])),
      'date': int(dbPost['date']),
      'html': dbPost['messagetext'],
      'sig': dbPost['sig'] if dbPost['sig'] != 'False' else None
    }
    self.set(postInfo)

    # this needs to be after the topic is set.
    # get number of posts in this topic up to this post.
    numPosts = int(self.db.table("posts").fields("COUNT(*)").where("ll_messageid < " + str(int(self.id)), ll_topicid=str(self.topic.id)).firstValue())
    self.set({
      'page': int(numPosts * 1.0 / 50) + 1
      })
    return self

class BaseList(BaseObject):
  '''
  Base list object for ETI unofficial API.
  '''
  def __init__(self, db):
    self.db = db
    self._table = self._user = self._topic = self._order = None
    self._start = 0
    self._limit = 50
  def user(self, user):
    self._user = user
    return self
  def topic(self, topic):
    self._topic = topic
    return self
  def order(self, order):
    self._order = order
    return self
  def start(self, start):
    self._start = int(start)
    return self
  def limit(self, limit):
    self._limit = int(limit)
    return self
  def search(self, query=None):
    self.db.table(self._table)
    if self._user is not None:
      self.db.where(userid=str(int(self._user.id)))
    if self._topic is not None:
      self.db.where(ll_topicid=str(int(self._topic.id)))
    if self._order is not None:
      self.db.order(self._order)
    self.db.start(self._start).limit(self._limit)
    return self

class PostList(BaseList):
  '''
  Post list object for ETI unofficial API.
  '''
  def __init__(self, db):
    super(PostList, self).__init__(db)
    self._table = "posts"
    self._order = "`date` DESC"
  def search(self, query=None):
    super(PostList, self).search(query=query)
    self.db.fields("`ll_messageid`")
    return [Post(self.db, int(post['ll_messageid'])) for post in self.db.query()]

class TopicList(BaseList):
  '''
  Topic list object for ETI unofficial API.
  '''
  def __init__(self, db, tags=None):
    super(TopicList, self).__init__(db)
    self._table = "topics"
    self._tags = tags
    self._firstPost = True
    self._order = "`lastPostTime` DESC"
  def tags(self, tags):
    self._tags = tags
    return self
  def firstPost(self, firstPost):
    self._firstPost = bool(firstPost)
    return self
  def search(self, query=None):
    super(TopicList, self).search(query=query)
    self.db.fields("`ll_topicid`")
    if self._tags is not None:
      self.db.table("tags_topics").join("`topics` ON `ll_topicid` = `topic_id`").where(tag_id=[str(int(tag.id)) for tag in self._tags])
    if query is not None:
      self.db.match(['`topics`.`title`'], query)
    return [Topic(self.db, int(topic['ll_topicid'])) for topic in self.db.query()]

class Topic(BaseObject):
  '''
  Topic-loading object for ETI unofficial API.
  '''
  def __init__(self, db, id):
    self.db = db
    self.id = id
    if not isinstance(id, int) or int(id) < 1:
      raise InvalidTopicError(self)

  def __len__(self):
    return len(self.posts)

  def __contains__(self, post):
    return post.id in self._postIDs

  def __index__(self):
    return self.id

  def __hash__(self):
    return self.id

  def __eq__(self, topic):
    return self.id == topic.id

  def load(self):
    """
    Fetches topic info.
    """
    dbTopic = self.db.table("topics").where(ll_topicid=str(self.id)).firstRow()
    if not dbTopic:
      raise InvalidTopicError(self)
    topicInfo = {
      'id': int(dbTopic['ll_topicid']),
      'post_count': int(dbTopic['postCount']),
      'last_post_time': int(dbTopic['lastPostTime']),
      'title': dbTopic['title'],
      'user': User(self.db, int(dbTopic['userid']))
    }
    self.set(topicInfo)
    return self

  @property
  def posts(self):
    """
    Fetches topic posts.
    """
    dbTopicPosts = self.db.table("posts").where(ll_topicid=str(self.id)).order("`ll_messageid` ASC").query()
    return [Post(self.db, int(dbPost['ll_messageid'])) for dbPost in dbTopicPosts]

  @property
  def users(self):
    """
    Fetches topic users.
    """
    dbTopicUsers = self.db.fields("`userid`", "COUNT(*) AS `count`").table("posts").where(ll_topicid=str(self.id)).group("userid").order("`count` DESC").query()
    return [{'user': User(self.db, int(dbUser['userid'])), 'posts': int(dbUser['count'])} for dbUser in dbTopicUsers]

class User(BaseObject):
  '''
  User-loading object for ETI unofficial API.
  '''
  def __init__(self, db, id):
    self.db = db
    self.id = id
    if not isinstance(id, int) or int(id) < 0:
      raise InvalidUserError(self)

  def __len__(self):
    return len(self.posts)

  def __contains__(self, post):
    return post.id in self._postIDs

  def __index__(self):
    return self.id

  def __hash__(self):
    return self.id

  def __eq__(self, topic):
    return self.id == topic.id

  def load(self):
    """
    Fetches user info.
    """
    if self.id == 0:
      # Anonymous user.
      dbUser = collections.defaultdict(int)
      names = [{'name': 'Human', 'date': None}]
    else:
      dbUser = self.db.table("users").where(id=str(self.id)).firstRow()
      if not dbUser:
        raise InvalidUserError(self)
      dbNames = self.db.table("user_names").where(user_id=str(self.id)).order("`date` DESC").query()
      names = [{'name': name['name'], 'date': int(pytz.utc.localize(name['date']).strftime('%s'))} for name in dbNames]
    userInfo = {
      'id': int(dbUser['id']),
      'names': names,
      'created': int(dbUser['created']),
      'last_active': int(dbUser['lastactive']),
      'good_tokens': int(dbUser['good_tokens']),
      'bad_tokens': int(dbUser['bad_tokens']),
      'tokens': int(dbUser['contrib_tokens']),
      'signature': dbUser['signature'] if dbUser['signature'] != "NULL" else None,
      'quote': dbUser['quote'] if dbUser['quote'] != "NULL" else None,
      'email': dbUser['email'] if dbUser['email'] != "NULL" else None,
      'im': dbUser['im'] if dbUser['im'] != "NULL" else None,
      'picture': dbUser['picture'] if dbUser['picture'] != "NULL" else None,
      'status': int(dbUser['status']),
    }
    self.set(userInfo)
    return self

  def is_authenticated(self):
    return not self.is_anonymous()

  def is_active(self):
    return self.is_authenticated()

  def is_anonymous(self):
    return self.id == 0

  def get_id(self):
    return unicode(self.id)

  @property
  def posts(self):
    """
    Fetches user posts.
    """
    dbUserPosts = self.db.table("posts").fields("`ll_messageid`").where(userid=str(self.id)).order("`date` DESC").query()
    return [Post(self.db, int(dbPost['ll_messageid'])) for dbPost in dbUserPosts]

  @property
  def topics(self):
    """
    Fetches user topics.
    """
    dbUserTopics = self.db.table("topics").fields("`ll_topicid`").where(userid=str(self.id)).order("`lastPostTime` DESC").query()
    return [Topic(self.db, int(dbTopic['ll_topicid'])) for dbTopic in dbUserTopics]

class Tag(BaseObject):
  '''
  Tag-loading object for ETI unofficial API.
  '''
  def __init__(self, db, title):
    self.db = db
    self.title = title
    if not isinstance(title, basestring):
      raise InvalidTagError(self)
    self._id = None

  def __contains__(self, topic):
    return topic.id in self._topicIDs

  def __index__(self):
    return hash(self.title)

  def __hash__(self):
    return hash(self.title)

  def __eq__(self, tag):
    return self.title == tag.title

  def load(self):
    """
    Fetches topic info.
    """
    dbTag = self.db.table("tags").where(name=str(self.title)).firstRow()
    if not dbTag:
      raise InvalidTagError(self)
    tagID = self.id
    dbDependencies = self.db.table("tags_dependent").fields("name").join("`tags` ON `tags_dependent`.`parent_tag_id` = `tags`.`id`").where(child_tag_id=str(tagID)).list("name")
    dbDependencies = dbDependencies if dbDependencies else []
    dbForbiddens = self.db.table("tags_forbidden").fields("name").join("`tags` ON `tags_forbidden`.`forbidden_tag_id` = `tags`.`id`").where(tag_id=str(tagID)).list("name")
    dbForbiddens = dbForbiddens if dbForbiddens else []
    dbRelated = self.db.table("tags_related").fields("name").join("`tags` ON `tags_related`.`parent_tag_id` = `tags`.`id`").where(child_tag_id=str(tagID)).list("name")
    dbRelated = dbRelated if dbRelated else []

    tagInfo = {
      'title': dbTag['name'],
      'description': dbTag['description'],
      'access': int(dbTag['access']),
      'participation': int(dbTag['participation']),
      'permanent': int(dbTag['permanent']),
      'inceptive': int(dbTag['inceptive']),
      'dependent': dbDependencies,
      'forbidden': dbForbiddens,
      'related': dbRelated
    }
    self.set(tagInfo)
    return self

  @property
  def id(self):
    """
    Fetches tag ID for this title.
    """
    if self._id is None:
      tagID = self.db.table("tags").fields("id").where(name=str(self.title)).firstValue()
      if not tagID:
        raise InvalidTagError(self)
      self._id = int(tagID)
    return self._id

  @property
  def topics(self):
    """
    Fetches tag topics.
    """
    dbTagTopics = self.db.table("tags_topics").fields("topic_id").join("topics ON topics.ll_topicid = tags_topics.topic_id").where(tag_id=str(self.id)).order("topics.lastPostTime DESC").list("topic_id")
    return [Topic(self.db, int(topicID)) for topicID in dbTagTopics]