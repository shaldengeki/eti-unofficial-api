#!/usr/bin/env python
"""
  Unofficial ETI API server.
  Uses Flask and MySQLdb.
  Written by shaldengeki <shaldengeki@gmail.com>
  Released under WTFPL <http://www.wtfpl.net/txt/copying>
"""

from flask import Flask, request, jsonify, session, g, redirect, url_for, abort, render_template, flash
import DbConn
from eti import InvalidTopicError, InvalidPostError, InvalidUserError, Topic, Post, User, TopicList

app = Flask(__name__)

DB_CREDENTIALS_FILE = "credentials.txt"
MYSQL_USERNAME,MYSQL_PASSWORD,MYSQL_DB = open(DB_CREDENTIALS_FILE, 'r').read().strip().split(',')

app.config.from_object(__name__)

def jsonify_list(outputList, key):
  resp = jsonify({key: outputList})
  resp.status_code = 200
  return resp

def jsonify_object(outputObj):
  """
  Takes an object (or None) and returns a proper json response object.
  """
  outputObj = outputObj.dict()
  status = 200
  if outputObj is None:
    status = 404
    outputObj = {}
  resp = jsonify(outputObj)
  resp.status_code = status
  return resp

@app.before_request
def before_request():
  g.db = DbConn.DbConn(app.config['MYSQL_USERNAME'], app.config['MYSQL_PASSWORD'], app.config['MYSQL_DB'])

@app.teardown_request
def teardown_request(exception):
  g.db.close()

@app.route('/')
def api_root():
  return 'This is the server for the ETIStats unofficial API.'

@app.route('/topics')
def api_topics():
  topicList = TopicList(g.db)
  if 'user' in request.args:
    filterUser = User(g.db, int(request.args['user']))
    topicList.user(filterUser)
  if 'tag' in request.args:
    tagNames = request.args.getlist('tag')
    # TODO
  if 'start' in request.args:
    topicList.start(int(request.args['start']))
  if 'limit' in request.args:
    topicLimit = 1000 if int(request.args['limit']) > 1000 or int(request.args['limit']) < 1 else int(request.args['limit'])
    topicList.limit(topicLimit)
  searchTopics = [topic.load().dict() for topic in topicList.search()]
  return jsonify_list(searchTopics, 'topics')

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
    try:
      topicObj = Topic(g.db, topicid)
      posts = [post.load().dict() for post in topicObj.posts]
    except InvalidTopicError:
      posts = None
    return jsonify_list(posts, 'posts')
  except Exception, e:
    return str(e)

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
def api_user_posts(userid):
  try:
    try:
      userObj = User(g.db, userid)
      posts = [post.load().dict() for post in userObj.posts]
    except InvalidUserError:
      posts = None
    resp = jsonify({'posts': posts})
    resp.status_code = 200
    return resp
  except Exception, e:
    return str(e)

@app.route('/users/<int:userid>/topics')
def api_user_topics(userid):
  try:
    try:
      userObj = User(g.db, userid)
      topics = [topic.load().dict() for topic in userObj.topics]
    except InvalidUserError:
      topics = None
    resp = jsonify({'topics': topics})
    resp.status_code = 200
    return resp
  except Exception, e:
    return str(e)

if __name__ == '__main__':
  app.run()