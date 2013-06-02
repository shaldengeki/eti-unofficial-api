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
    self.clearParams()

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

  def clearParams(self):
    """
    Clears query parameters.
    """
    self._table = self._order = self._group = None
    self._fields = []
    self._joins = []
    self._wheres = []
    self._params = []
    self._start = 0
    self._limit = 50
    return self

  def connect(self):
    try:
      self._conn = MySQLdb.connect('localhost', self.username, self.password, self.database, charset="utf8", use_unicode=True, cursorclass=MySQLdb.cursors.SSDictCursor)
      self._cursor = None
    except MySQLdb.Error, e:
      print "Error connecting to MySQL database %d: %s to database: %s" % (e.args[0],e.args[1],self.database)
      raise
    return True

  def table(self, table):
    self._table = "".join(["`", table, "`"])
    return self

  def fields(self, *args):
    self._fields.extend(args)
    return self

  def join(self, join, joinType="INNER"):
    self._joins.append(" ".join([joinType, "JOIN", join]))
    return self

  def where(self, *args, **kwargs):
    for entry in args:
      self._wheres.append(entry)
    for field, value in kwargs.items():
      if isinstance(value, (basestring, int, float, long, bool)):
        # if scalar, assume it's a direct equals.
        self._wheres.append("".join(["`", field, "` = %s"]))
        self._params.extend([value])
      else:
        # if not scalar, assume it's an IN query.
        self._wheres.append("".join(["`", field, "` IN (", ",".join(["%s"] * len(value)), ")"]))
        self._params.extend(value)
    return self

  def match(self, fields, query):
    # WHERE MATCH(fields) AGAINST(query IN BOOLEAN MODE)
    self._wheres.append("MATCH(" + ",".join(fields) + ") AGAINST(%s IN BOOLEAN MODE)")
    self._params.extend([query])
    return self

  def group(self, field):
    self._group = field if instanceof(field, list) else [field]
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

  def query(self, newCursor=False):
    fields = ["*"] if not self._fields else self._fields
    searchQuery = " ".join(["SELECT", ",".join(fields), "FROM", self._table, " ".join(self._joins), " ".join(["WHERE", "&&".join(self._wheres)]) if self._wheres else "", " ".join(["GROUP BY", ",".join(self._group)]) if self._group else "", " ".join(["ORDER BY", str(self._order)]) if self._order else "", "LIMIT %s, %s"])
    self._params.extend([int(self._start), int(self._limit)])
    try:
      if newCursor:
        cursor = self.conn.cursor()
      else:
        cursor = self.cursor
      cursor.execute(searchQuery, self._params)
    except (AttributeError, MySQLdb.OperationalError):
      # lost connection. reconnect and re-query.
      if not self.connect():
        print "Unable to reconnect to MySQL."
        raise
      cursor = self.cursor
      cursor.execute(searchQuery, self._params)
    self.clearParams()
    return cursor

  def list(self, valField, newCursor=False):
    if not isinstance(valField, basestring):
      return False
    queryCursor = self.query(newCursor=newCursor)
    if not queryCursor:
      return False
    return [result[valField] for result in queryCursor]

  def dict(self, keyField=None, valField=None, newCursor=False):
    if valField is None:
      return False
    if keyField is None:
      keyField = u'id'
    queryResults = {}
    queryCursor = self.query(newCursor=newCursor)
    if not queryCursor:
      return False
    row = queryCursor.fetchone()
    while row is not None:
      queryResults[row[keyField]] = row[valField]
      row = queryCursor.fetchone()
    return queryResults

  def firstRow(self, newCursor=False):
    queryCursor = self.limit(1).query(newCursor=newCursor)
    if not queryCursor:
      return False
    firstRow = queryCursor.fetchone()
    queryCursor.close()
    if not newCursor:
      self._cursor = None
    return firstRow

  def firstValue(self, newCursor=False):
    firstRow = self.limit(1).firstRow(newCursor=newCursor)
    if not firstRow:
      return False
    rowKeys = firstRow.keys()
    return firstRow[rowKeys[0]]

  def close(self):
    self.conn.close()
    self._conn = None