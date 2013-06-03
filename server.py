#!/usr/bin/env python
"""
  Unofficial ETI API server.
  Uses Flask and MySQLdb.
  Written by shaldengeki <shaldengeki@gmail.com>
  Released under WTFPL <http://www.wtfpl.net/txt/copying>
"""

from flask import Flask, request, jsonify, g, redirect, url_for, abort, render_template, flash
import flask_login
from functools import wraps
import urllib2
import urllib
import sys, os

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

@app.route('/')
def api_root():
  return 'This is the server for the ETIStats unofficial API.'

@app.route('/topics')
def api_topics():
  try:
    topicList = TopicList(g.db)
    query = request.args['query'] if 'query' in request.args else None
    if 'user' in request.args:
      try:
        filterUser = User(g.db, int(request.args['user']))
      except InvalidUserError, e:
        return not_found()
      topicList.user(filterUser)
    if 'tag' in request.args:
      tagNames = request.args.getlist('tag')
      # TODO
    if 'start' in request.args:
      requestedStart = int(request.args['start'])
      topicList.start(0 if requestedStart < 0 else requestedStart)
    if 'limit' in request.args:
      topicLimit = 1000 if int(request.args['limit']) > 1000 or int(request.args['limit']) < 1 else int(request.args['limit'])
      topicList.limit(topicLimit)
    searchTopics = [topic.dict() for topic in topicList.search(query=query)]
    return jsonify_list(searchTopics, 'topics')
  except Exception as e:
    return str(e)

@app.route('/topics/<int:topicid>')
def api_topic(topicid):
  try:
    topicObj = Topic(g.db, topicid).load()
  except InvalidTopicError:
    topicObj = None
  return jsonify_object(topicObj)

@app.route('/topics/<int:topicid>/posts')
def api_topic_posts(topicid):
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
  searchPosts = [post.dict() for post in postList.search()]
  return jsonify_list(searchPosts, 'posts')

@app.route('/topics/<int:topicid>/users')
def api_topic_users(topicid):
  try:
    users = [{'user': user['user'].load().dict(), 'posts': int(user['posts'])} for user in Topic(g.db, topicid).users]
  except InvalidTopicError:
    users = None
  return jsonify_list(users, 'users')

@app.route('/posts')
def api_posts():
  return 'List of ' + url_for('api_posts')

@app.route('/posts/<int:postid>')
def api_post(postid):
  try:
    postObj = Post(g.db, postid).load()
    postObj.topic = postObj.topic.dict()
  except InvalidPostError:
    postObj = None
  return jsonify_object(postObj)

@app.route('/users')
def api_users():
  return 'List of ' + url_for('api_users')

@app.route('/users/<int:userid>')
def api_user(userid):
  try:
    userObj = User(g.db, userid).load()
  except InvalidUserError:
    userObj = None
  return jsonify_object(userObj)

@app.route('/users/<int:userid>/posts')
@flask_login.login_required
def api_user_posts(userid):
  try:
    userObj = User(g.db, userid)
  except InvalidUserError:
    return not_found()
  postList = PostList(g.db).user(userObj)
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
  searchPosts = [post.load().dict() for post in postList.search()]
  return jsonify_list(searchPosts, 'posts')

@app.route('/users/<int:userid>/topics')
@flask_login.login_required
def api_user_topics(userid):
  try:
    userObj = User(g.db, userid)
  except InvalidUserError:
    return not_found()
  topicList = TopicList(g.db).user(userObj)
  query = request.args['query'] if 'query' in request.args else None
  if 'tag' in request.args:
    tagNames = request.args.getlist('tag')
    # TODO
  if 'limit' in request.args:
    requestedLimit = int(request.args['limit'])
    topicList.limit(1000 if requestedLimit > 1000 or requestedLimit < 1 else requestedLimit)
  if 'start' in request.args:
    requestedStart = int(request.args['start'])
    topicList.start(0 if requestedStart < 0 else requestedStart)
  searchTopics = [post.load().dict() for post in topicList.search(query=query)]
  return jsonify_list(searchTopics, 'topics')

@app.route('/tags')
def api_tags():
  return 'List of ' + url_for('api_tags')

@app.route('/tags/<title>')
def api_tag(title):
  try:
    try:
      tagObj = Tag(g.db, title).load()
    except InvalidTagError:
      tagObj = None
    return jsonify_object(tagObj)
  except Exception as e:
    return str(e)

@app.route('/tags/<title>/topics')
def api_tag_topics(title):
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
  searchTopics = [post.load().dict() for post in topicList.search(query=query)]
  return jsonify_list(searchTopics, 'topics')

@app.route('/login')
def api_login():
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
  flask_login.logout_user()
  return redirect(url_for('api_root'))

if __name__ == '__main__':
  app.run()