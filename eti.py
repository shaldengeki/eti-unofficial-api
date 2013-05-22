#!/usr/bin/env python
"""
  Topic and post classes for ETI unofficial API.
  Uses Flask, MySQLdb, and pytz.
  Written by shaldengeki <shaldengeki@gmail.com>
  Released under WTFPL <http://www.wtfpl.net/txt/copying>
"""

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

class BaseObject(object):
  '''
  Base object with common features.
  '''
  def dict(self):
    """
    Filters out all non-serializable attributes of this object.
    """
    resultDict = {}
    for k,v in self.__dict__.iteritems():
      if isinstance(v, BaseObject):
        v = v.dict()
      elif k == 'db':
        continue
      resultDict[k] = v
    return resultDict

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

  def __str__(self):
    return str(self.dict())

  def __contains__(self, searchString):
    return searchString in self.html

  def __index__(self):
    return self.id

  def __hash__(self):
    return self.id

  def __eq__(self, post):
    return self.id == post.id

  def set(self, attrDict):
    """
    Sets attributes of this post object with keys found in dict.
    """
    for key in attrDict:
      setattr(self, key, attrDict[key])
    return self

  def load(self):
    """
    Fetches post info.
    """
    dbPost = self.db.queryFirstRow("SELECT * FROM `posts` WHERE `ll_messageid` = %s LIMIT 1", [str(self.id)])
    if not dbPost:
      raise InvalidPostError(self)
    postInfo = {
      'id': int(dbPost['ll_messageid']),
      'topic': Topic(self.db, int(dbPost['ll_topicid'])),
      'user': int(dbPost['userid']),
      'date': int(dbPost['date']),
      'html': dbPost['messagetext'],
      'sig': dbPost['sig'] if dbPost['sig'] != 'False' else None
    }
    self.set(postInfo)
    return self

class Topic(BaseObject):
  '''
  Topic-loading object for ETI unofficial API.
  '''
  def __init__(self, db, id):
    self.db = db
    self.id = id
    if not isinstance(id, int) or int(id) < 1:
      raise InvalidTopicError(self)

  def __str__(self):
    return str(self.dict())

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

  def set(self, attrDict):
    """
    Sets attributes of this topic object with keys found in dict.
    """
    for key in attrDict:
      setattr(self, key, attrDict[key])
    return self

  def load(self):
    """
    Fetches topic info.
    """
    dbTopic = self.db.queryFirstRow("SELECT * FROM `topics` WHERE `ll_topicid` = %s LIMIT 1", [str(self.id)])
    if not dbTopic:
      raise InvalidTopicError(self)
    topicInfo = {
      'id': int(dbTopic['ll_topicid']),
      'post_count': int(dbTopic['postCount']),
      'last_post_time': int(dbTopic['lastPostTime']),
      'title': dbTopic['title'],
      'user_id': int(dbTopic['userid'])
    }
    self.set(topicInfo)
    return self

  @property
  def posts(self):
    """
    Fetches topic posts.
    """
    dbTopicPosts = self.db.queryDB("SELECT * FROM `posts` WHERE `ll_topicid` = %s ORDER BY `ll_messageid` ASC", [str(self.id)])
    return [Post(self.db, int(dbPost['ll_messageid'])) for dbPost in dbTopicPosts]

class User(BaseObject):
  '''
  User-loading object for ETI unofficial API.
  '''
  def __init__(self, db, id):
    self.db = db
    self.id = id
    if not isinstance(id, int) or int(id) < 1:
      raise InvalidTopicError(self)

  def __str__(self):
    return str(self.dict())

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

  def set(self, attrDict):
    """
    Sets attributes of this topic object with keys found in dict.
    """
    for key in attrDict:
      setattr(self, key, attrDict[key])
    return self

  def load(self):
    """
    Fetches topic info.
    """
    dbUser = self.db.queryFirstRow("SELECT * FROM `users` WHERE `id` = %s LIMIT 1", [str(self.id)])
    if not dbUser:
      raise InvalidUserError(self)
    dbNames = self.db.queryDB("SELECT * FROM `user_names` WHERE `user_id` = %s ORDER BY `date` DESC", [str(self.id)])
    names = [{'name': name['name'], 'date': int(pytz.utc.localize(name['date']).strftime('%s'))} for name in dbNames]
    userInfo = {
      'id': int(dbUser['id']),
      'names': [name for name in dbNames] if dbNames else [],
      'created': int(dbUser['created']),
      'last_active': int(dbUser['lastactive']),
      'good_tokens': int(dbUser['good_tokens']),
      'bad_tokens': int(dbUser['bad_tokens']),
      'tokens': int(dbUser['contrib_tokens']),
      'signature': dbUser['signature'],
      'quote': dbUser['quote'],
      'email': dbUser['email'],
      'im': dbUser['im'],
      'picture': dbUser['picture'],
      'status': int(dbUser['status']),
    }
    self.set(userInfo)
    return self

  @property
  def posts(self):
    """
    Fetches user posts.
    """
    dbUserPosts = self.db.queryDB("SELECT `ll_messageid` FROM `posts` WHERE `userid` = %s ORDER BY `date` DESC", [str(self.id)])
    return [Post(self.db, int(dbPost['ll_messageid'])) for dbPost in dbUserPosts]