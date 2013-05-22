#!/usr/bin/env python
"""
  Unofficial ETI API server.
  Uses Flask and MySQLdb.
  Written by shaldengeki <shaldengeki@gmail.com>
  Released under WTFPL <http://www.wtfpl.net/txt/copying>
"""

from flask import Flask, request, jsonify, session, g, redirect, url_for, abort, render_template, flash
import DbConn
from eti import InvalidTopicError, InvalidPostError, InvalidUserError, Topic, Post, User

app = Flask(__name__)

DB_CREDENTIALS_FILE = "credentials.txt"
MYSQL_USERNAME,MYSQL_PASSWORD,MYSQL_DB = open(DB_CREDENTIALS_FILE, 'r').read().strip().split(',')

app.config.from_object(__name__)

def json_response(outputObj):
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
  return 'List of ' + url_for('api_topics')

@app.route('/topics/<int:topicid>')
def api_topic(topicid):
  try:
    try:
      topicObj = Topic(g.db, topicid).load()
    except InvalidTopicError:
      topicObj = None
    return json_response(topicObj)
  except Exception, e:
    return str(e)

@app.route('/topics/<int:topicid>/posts')
def api_topic_posts(topicid):
  try:
    try:
      topicObj = Topic(g.db, topicid)
      posts = [post.load().dict() for post in topicObj.posts]
    except InvalidTopicError:
      posts = None
    resp = jsonify({'posts': posts})
    resp.status_code = 200
    return resp
  except Exception, e:
    return str(e)

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
  return json_response(postObj)

@app.route('/users')
def api_users():
  return 'List of ' + url_for('api_users')

@app.route('/users/<int:userid>')
def api_user(userid):
  try:
    try:
      userObj = User(g.db, userid).load()
    except InvalidUserError:
      userObj = None
    return json_response(userObj)
  except Exception, e:
    return str(e)

# @app.route('/users/<int:userid>/posts')
# def api_topic_posts(userid):
#   try:
#     try:
#       userObj = User(g.db, userid)
#       posts = [post.load().dict() for post in userObj.posts]
#     except InvalidUserError:
#       posts = None
#     resp = jsonify({'posts': posts})
#     resp.status_code = 200
#     return resp
#   except Exception, e:
#     return str(e)

if __name__ == '__main__':
  app.run()