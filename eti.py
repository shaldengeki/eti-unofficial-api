#!/usr/bin/env python
"""
  Topic and post classes for ETI unofficial API.
  Uses Flask, MySQLdb, and pytz.
  Written by shaldengeki <shaldengeki@gmail.com>
  Released under WTFPL <http://www.wtfpl.net/txt/copying>
"""

import __builtin__
import collections
import json
import pytz

def getBuiltIn(name):
  return getattr(__builtin__, name)

def recursiveSerialize(item):
  resultDict = {}
  try:
    items = item.__dict__.iteritems()
  except AttributeError:
    try:
      items = item.iteritems()
    except AttributeError:
      # we've passed in a scalar. just return it.
      return item
  for k,v in items:
    if isinstance(v, BaseObject):
      v = v.dict()
    elif k == 'db' or k.startswith('_'):
      continue
    elif isinstance(v, list):
      v = [recursiveSerialize(x) for x in v]
    elif isinstance(v, dict):
      v = recursiveSerialize(v)
    resultDict[k] = v
  return resultDict

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
      "Tag Title: " + unicode(self.tag.name)
      ])

class BaseObject(object):
  '''
  Base object with common features.
  '''
  dbFields = {}
  def __str__(self):
    return str(self.dict())

  def dict(self):
    """
    Filters out all non-serializable attributes of this object.
    """
    return recursiveSerialize(self)

  def set(self, attrDict):
    """
    Sets attributes of this post object with keys found in dict.
    """
    for key in attrDict:
      setattr(self, key, attrDict[key])
    return self

  def setDB(self, attrDict):
    """
      Sets attributes of this object with database fields found in dict, translated into object attributes using dbFields.
    """
    translatedDict = {}
    for dbField in attrDict:
      if dbField in self.dbFields:
        if attrDict[dbField] is None:
          translatedDict[self.dbFields[dbField][1]] = None
        else:
          translatedDict[self.dbFields[dbField][1]] = getBuiltIn(self.dbFields[dbField][0])(attrDict[dbField])
    self.set(translatedDict)
    return self

class Post(BaseObject):
  '''
  Post-loading object for ETI unofficial API.
  '''
  dbFields = {
    'll_messageid': ('int', 'id'),
    'date': ('int', 'date'),
    'messagetext': ('unicode', 'html'),
    'sig': ('unicode', 'sig')
  }
  def __init__(self, db, id):
    self.db = db
    self.id = id
    if not isinstance(self.id, (int, long)) or int(self.id) < 1:
      raise InvalidPostError(self)
    else:
      self.id = int(self.id)

  def __contains__(self, searchString):
    return searchString in self.html

  def __index__(self):
    return self.id

  def __hash__(self):
    return self.id

  def __eq__(self, post):
    return self.id == post.id

  def setDB(self, attrDict):
    if 'sig' in attrDict:
      attrDict['sig'] = attrDict['sig'] if attrDict['sig'] != 'False' else None
    postTopic = Topic(self.db, int(attrDict['ll_topicid']))
    postUser = User(self.db, int(attrDict['userid']))
    self.set({
      'topic': postTopic.setDB(attrDict),
      'user': postUser.setDB(attrDict)
    })
    return super(Post, self).setDB(attrDict)

  def load(self, includes=None):
    """
    Fetches post info.
    """
    self.db.table("posts").fields("posts.*").where(ll_messageid=self.id)
    if includes is not None:
      for obj in includes:
        if obj == 'topic':
          self.db.fields('topics.*')
          self.db.join('topics ON topics.ll_topicid=posts.ll_topicid')
        elif obj == 'user':
          self.db.fields('users.*', 'user_names.name')
          self.db.join('users ON users.id=posts.userid')
          self.db.join('user_names ON user_names.user_id=users.id')
          self.db.join('user_names un2 ON un2.user_id=users.id AND user_names.date < un2.date', joinType="LEFT OUTER")
          self.db.where("un2.date IS NULL")

    dbPost = self.db.firstRow(newCursor=True)
    if not dbPost:
      raise InvalidPostError(self)

    self.setDB(dbPost)

    # this needs to be after the topic is set.
    foo = self.getPage()
    return self

  def getPage(self):
    if not hasattr(self, 'topic'):
      self.load()
    # get number of posts in this topic up to this post.
    numPosts = int(self.db.table("posts").fields("COUNT(*)").where("ll_messageid < " + str(int(self.id)), ll_topicid=str(self.topic.id)).firstValue(newCursor=True))
    pageNum = int(numPosts * 1.0 / 50) + 1
    self.set({
      'page': pageNum
    })
    return pageNum

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
    self._order = "date DESC"
  def search(self, query=None, includes=None):
    super(PostList, self).search(query=query)
    self.db.fields('posts.*')
    if includes is not None:
      for include in includes:
        if include == 'user':
          self.db.fields('users.*', 'user_names.name')
          self.db.join('users ON posts.userid=users.id')
          self.db.join('user_names ON user_names.user_id=users.id')
          self.db.join('user_names un2 ON un2.user_id=users.id AND user_names.date < un2.date', joinType="LEFT OUTER")
          self.db.where("un2.date IS NULL")
        elif include == 'topic':
          self.db.fields('topics.*')
          self.db.join('topics ON posts.ll_topicid=topics.ll_topicid')

    resultPosts = []
    for post in self.db.query():
      newPost = Post(self.db, post['ll_messageid'])
      resultPosts.append(newPost.setDB(post))

    # needs to be outside of the query() loop since getPage() pulls from the db
    [post.getPage() for post in resultPosts]
    return resultPosts

class Topic(BaseObject):
  '''
  Topic-loading object for ETI unofficial API.
  '''
  dbFields = {
    'll_topicid': ('int', 'id'),
    'title': ('unicode', 'title'),
    'postCount': ('int', 'post_count'),
    'lastPostTime': ('int', 'last_post_time')
  }
  def __init__(self, db, id):
    self.db = db
    self.id = id
    if not isinstance(self.id, (int, long)) or int(self.id) < 1:
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

  def setDB(self, attrDict):
    if 'userid' in attrDict:
      topicUser = User(self.db, int(attrDict['userid']))
      self.set({
        'user': topicUser.setDB(attrDict)
      })
    return super(Topic, self).setDB(attrDict)

  def load(self, includes=None):
    """
    Fetches topic info.
    """

    self.db.table("topics").fields('topics.*').where(ll_topicid=str(self.id))

    includeTags = False    
    if includes is not None:
      for include in includes:
        if include == 'tags':
          includeTags = True
        elif include == 'user':
          self.db.fields('users.*', 'user_names.name')
          self.db.join('users ON users.id=topics.userid')
          self.db.join('user_names ON user_names.user_id=users.id')
          self.db.join('user_names un2 ON un2.user_id=users.id AND user_names.date < un2.date', joinType="LEFT OUTER")
          self.db.where("un2.date IS NULL")

    dbTopic = self.db.firstRow(newCursor=True)
    if not dbTopic:
      raise InvalidTopicError(self)
    self.setDB(dbTopic)

    if includeTags:
      self.set({
        'tags': self.getTags()
      })

    return self

  def getTags(self):
    """
    Fetches topic tags.
    """
    dbTopicTags = self.db.table("tags_topics").fields("name").join("tags ON tags.id = tags_topics.tag_id").where(topic_id=str(self.id)).order("name ASC").query()
    return [Tag(self.db, topic['name']) for topic in dbTopicTags]

  @property
  def posts(self):
    """
    Fetches topic posts.
    """
    dbTopicPosts = self.db.table("posts").where(ll_topicid=str(self.id)).order("ll_messageid ASC").query()
    return [Post(self.db, int(dbPost['ll_messageid'])).setDB(dbPost) for dbPost in dbTopicPosts]

  @property
  def users(self):
    """
    Fetches topic users.
    """
    dbTopicUsers = self.db.fields("userid", "COUNT(*) AS count").table("posts").where(ll_topicid=str(self.id)).group("userid").order("count DESC").query()
    return [{'user': User(self.db, int(dbUser['userid'])), 'posts': int(dbUser['count'])} for dbUser in dbTopicUsers]

class TopicList(BaseList):
  '''
  Topic list object for ETI unofficial API.
  '''
  def __init__(self, db, tags=None):
    super(TopicList, self).__init__(db)
    self._table = "topics"
    self._includeTags = []
    self._excludeTags = []
    self._firstPost = True
    self._order = "lastPostTime DESC"
    if tags is not None:
      self.tags(tags)
  def includeTag(self, tag):
    self._includeTags.append(tag)
    return self
  def excludeTag(self, tag):
    self._excludeTags.append(tag)
    return self
  def tags(self, tags):
    self._includeTags = tags
    return self
  def firstPost(self, firstPost):
    self._firstPost = bool(firstPost)
    return self
  def search(self, query=None, includes=None):
    if self._includeTags:
      includeTagIDs = [str(int(tag.id)) for tag in self._includeTags]
    super(TopicList, self).search(query=query)
    if self._includeTags:
      self.db.table("tags_topics").fields('tags_topics.*').join("topics ON topics.ll_topicid=tags_topics.topic_id").where(tag_id=includeTagIDs)
    self.db.fields('topics.*')

    includeTags = False    
    if includes is not None:
      for include in includes:
        if include == 'tags':
          includeTags = True
        elif include == 'user':
          self.db.fields('users.*')
          self.db.join('users ON userid=users.id')

    if query is not None:
      self.db.match(['topics.title'], query)

    resultTopics = []
    topics = self.db.list()
    for topic in topics:
      newTopic = Topic(self.db, topic['ll_topicid']).setDB(topic)
      if includes:
        newTopic.load(includes=includes)
      resultTopics.append(newTopic)

    if includeTags or self._excludeTags:
      [topic.set({'tags': topic.getTags()}) for topic in resultTopics]

    if self._excludeTags:
      [tag.load() for tag in self._excludeTags]
      resultTopics = [topic for topic in resultTopics if not any([excludeTag in topic.tags for excludeTag in self._excludeTags])]

    return resultTopics

class User(BaseObject):
  '''
  User-loading object for ETI unofficial API.
  '''
  dbFields = {
    'id': ('int', 'id'),
    'name': ('unicode', 'name'),
    'created': ('int', 'created'),
    'lastactive': ('int', 'last_active'),
    'good_tokens': ('int', 'good_tokens'),
    'bad_tokens': ('int', 'bad_tokens'),
    'contrib_tokens': ('int', 'tokens'),
    'signature': ('unicode', 'signature'),
    'quote': ('unicode', 'quote'),
    'email': ('unicode', 'email'),
    'im': ('unicode', 'im'),
    'picture': ('unicode', 'picture'),
    'status': ('int', 'status')
  }
  def __init__(self, db, id):
    self.db = db
    self.id = id
    if not isinstance(id, (int, long)) or int(id) < 0:
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

  def setDB(self, attrDict):
    if 'signature' in attrDict:
      attrDict['signature'] = attrDict['signature'] if attrDict['signature'] != 'NULL' else None
    if 'quote' in attrDict:
      attrDict['quote'] = attrDict['quote'] if attrDict['quote'] != 'NULL' else None
    if 'email' in attrDict:
      attrDict['email'] = attrDict['email'] if attrDict['email'] != 'NULL' else None
    if 'im' in attrDict:
      attrDict['im'] = attrDict['im'] if attrDict['im'] != 'NULL' else None
    if 'picture' in attrDict:
      attrDict['picture'] = attrDict['picture'] if attrDict['picture'] != 'NULL' else None
    if 'name' in attrDict:
      attrDict['name'] = attrDict['name'] if attrDict['name'] != 'NULL' else None
    return super(User, self).setDB(attrDict)

  def load(self):
    """
    Fetches user info.
    """
    if self.id == 0:
      # Anonymous user.
      dbUser = collections.defaultdict(int)
      names = [{'name': 'Human', 'date': None}]
    else:
      dbUser = self.db.table("users").where(id=str(self.id)).firstRow(newCursor=True)
      if not dbUser:
        raise InvalidUserError(self)
      dbNames = self.db.table("user_names").where(user_id=str(self.id)).order("date DESC").query()
      names = [{'name': name['name'], 'date': int(pytz.utc.localize(name['date']).strftime('%s'))} for name in dbNames if name['date'] is not None]
    self.setDB(dbUser)
    self.set({
      'names': names,
      'name': max(names, key=lambda x: x['date'])['name'] if names else u''
    })
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
    dbUserPosts = self.db.table("posts").fields("ll_messageid").where(userid=str(self.id)).order("date DESC").query()
    return [Post(self.db, int(dbPost['ll_messageid'])) for dbPost in dbUserPosts]

  @property
  def topics(self):
    """
    Fetches user topics.
    """
    dbUserTopics = self.db.table("topics").fields("ll_topicid").where(userid=str(self.id)).order("lastPostTime DESC").query()
    return [Topic(self.db, int(dbTopic['ll_topicid'])) for dbTopic in dbUserTopics]

class Tag(BaseObject):
  '''
  Tag-loading object for ETI unofficial API.
  '''
  dbFields = {
    'id': ('int', 'id'),
    'access': ('int', 'access'),
    'participation': ('int', 'participation'),
    'permanent': ('int', 'permanent'),
    'inceptive': ('int', 'inceptive'),
    'name': ('unicode', 'name'),
    'description': ('unicode', 'description')
  }
  def __init__(self, db, title):
    self.db = db
    self.name = title
    if not isinstance(title, basestring):
      raise InvalidTagError(self)
    self._staff = self._dependents = self._forbiddens = self._relateds = None

  def __contains__(self, topic):
    return topic.id in self._topicIDs

  def __index__(self):
    return hash(self.name)

  def __hash__(self):
    return hash(self.name)

  def __eq__(self, tag):
    return self.name == tag.name

  def __getattr__(self, attr):
    self.load()
    if not hasattr(self, attr):
      raise AttributeError(attr + ' not found in object ' + self.__name__)
    return getattr(self, attr)

  def load(self):
    """
    Fetches topic info.
    """
    dbTag = self.db.table("tags").where(name=str(self.name)).firstRow(newCursor=True)
    if not dbTag:
      raise InvalidTagError(self)
    self.setDB(dbTag)

    return self

  def getId(self):
    tagID = self.db.table("tags").fields("id").where(name=str(self.name)).firstValue(newCursor=True)
    if not tagID:
      raise InvalidTagError(self)
    return int(tagID)

  def getStaff(self):
    if not hasattr(self, 'id'):
      self.load()
    dbTagStaff = self.db.table("tags_users").fields(*(["user_id", "role", 'users.*'])).join("users ON user_id = id").where(tag_id=self.id).order("role DESC, username ASC")
    resultStaff = []
    for user in dbTagStaff.query():
      newUser = User(self.db, user['user_id'])
      resultStaff.append({"role": int(user['role']), "user": newUser.setDB(user)})
    return resultStaff

  @property
  def staff(self):
    if self._staff is None:
      self._staff = self.getStaff()
    return self._staff

  def getDependencies(self):
    if not hasattr(self, 'id'):
      self.load()
    dbDependencies = self.db.table("tags_dependent").fields("name").join("tags ON tags_dependent.parent_tag_id = tags.id").where(child_tag_id=str(self.id))
    resultTags = []
    for tag in dbDependencies.query():
      newTag = Tag(self.db, tag['parent_tag_id'])
      resultTags.append(newTag.setDB(tag))
    return resultTags

  @property
  def dependent(self):
    if self._dependents is None:
      self._dependents = self.getDependencies()
    return self._dependents

  def getForbiddens(self):
    if not hasattr(self, 'id'):
      self.load()
    dbForbiddens = self.db.table("tags_forbidden").fields("name").join("tags ON tags_forbidden.forbidden_tag_id = tags.id").where(tag_id=str(self.id))
    resultTags = []
    for tag in dbForbiddens.query():
      newTag = Tag(self.db, tag['forbidden_tag_id'])
      resultTags.append(newTag.setDB(tag))
    return resultTags

  @property
  def forbidden(self):
    if self._forbiddens is None:
      self._forbiddens = self.getForbiddens()
    return self._forbiddens

  def getRelateds(self):
    if not hasattr(self, 'id'):
      self.load()
    dbRelateds = self.db.table("tags_related").fields("name").join("tags ON tags_related.parent_tag_id = tags.id").where(child_tag_id=str(self.id))
    resultTags = []
    for tag in dbRelateds.query():
      newTag = Tag(self.db, tag['parent_tag_id'])
      resultTags.append(newTag.setDB(tag))
    return resultTags

  @property
  def related(self):
    if self._relateds is None:
      self._relateds = self.getRelateds()
    return self._relateds

  @property
  def topics(self):
    """
    Fetches tag topics.
    """
    if not hasattr(self, 'id'):
      self.load()
    dbTagTopics = self.db.table("tags_topics").fields("topic_id").join("topics ON topics.ll_topicid = tags_topics.topic_id").where(tag_id=str(self.id)).order("topics.lastPostTime DESC").list("topic_id")
    return [Topic(self.db, int(topicID)) for topicID in dbTagTopics]
