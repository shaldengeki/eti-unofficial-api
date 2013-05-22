#!/usr/bin/env python
import MySQLdb
import MySQLdb.cursors 
import _mysql_exceptions

class DbConn(object):
  '''
  Simple database connection class to reconnect to MySQL if the connection times out.
  '''
  def __init__(self, username, password, database):
    self.username = username
    self.password = password
    self.database = database
    self._conn = self._cursor = None

  @property
  def conn(self):
    if self._conn is None:
      self.connect()
    return self._conn

  @property
  def cursor(self):
    if self._cursor is None:
      self._cursor = self.conn.cursor()
    return self._cursor

  def connect(self):
    try:
      self._conn = MySQLdb.connect('localhost', self.username, self.password, self.database, charset="utf8", use_unicode=True, cursorclass=MySQLdb.cursors.SSDictCursor)
      self._cursor = None
    except MySQLdb.Error, e:
      print "Error connecting to MySQL database %d: %s to database: %s" % (e.args[0],e.args[1],self.database)
      raise
    return True
  def queryDB(self, query, params=[], newCursor=False):
    try:
      if newCursor:
        cursor = self.conn.cursor()
      else:
        cursor = self.cursor
      cursor.execute(query, params)
    except (AttributeError, MySQLdb.OperationalError):
      # lost connection. reconnect and re-query.
      if not self.connect():
        print "Unable to reconnect to MySQL."
        raise
      cursor = self.cursor
      cursor.execute(query, params)
    return cursor
  def queryList(self, query, params=[], valField=None, newCursor=False):
    if valField is None:
      return False
    queryCursor = self.queryDB(query, params, newCursor=newCursor)
    if not queryCursor:
      return False
    return [result[valField] for result in queryCursor]
  def queryDict(self, query, params=[], keyField=None, valField=None, newCursor=False):
    if valField is None:
      return False
    if keyField is None:
      keyField = u'id'
    queryResults = {}
    queryCursor = self.queryDB(query, params, newCursor=newCursor)
    if not queryCursor:
      return False
    row = queryCursor.fetchone()
    while row is not None:
      queryResults[row[keyField]] = row[valField]
      row = queryCursor.fetchone()
    return queryResults
  def queryFirstRow(self, query, params=[], newCursor=False):
    queryCursor = self.queryDB(query, params, newCursor=newCursor)
    if not queryCursor:
      return False
    firstRow = queryCursor.fetchone()
    queryCursor.close()
    if not newCursor:
      self._cursor = None
    return firstRow
  def queryFirstValue(self, query, params=[], newCursor=False):
    firstRow = self.queryFirstRow(query, params, newCursor=newCursor)
    if not firstRow:
      return False
    rowKeys = firstRow.keys()
    return firstRow[rowKeys[0]]
  def close(self):
    self.conn.close()
    self._conn = None