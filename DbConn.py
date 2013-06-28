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

  def resetCursor(self, cursor=None):
    if cursor is None:
      try:
        self._cursor.close()
        self._cursor = None
      except AttributeError:
        # cursor hasn't been set.
        pass
    else:
      cursor.close()
      cursor = self.conn.cursor()
    return self

  def clearParams(self):
    """
    Clears query parameters.
    """
    self._type = "SELECT"
    self._table = self._order = self._group = None
    self._fields = []
    self._joins = []
    self._sets = []
    self._wheres = []
    self._values = []
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

  def select(self):
    self._type = "SELECT"
    return self

  def table(self, table):
    self._table = table
    return self

  def fields(self, *args):
    self._fields.extend(args)
    return self

  def join(self, join, joinType="INNER"):
    self._joins.append(" ".join([joinType, "JOIN", join]))
    return self

  def set(self, *args, **kwargs):
    for entry in args:
      self._sets.append(entry)
    for field, value in kwargs.items():
      if isinstance(value, (basestring, int, float, long, bool)):
        # if scalar, assume it's a direct equals.
        self._sets.append("".join([field, " = %s"]))
        self._params.extend([value])
      else:
        raise _mysql_exceptions.InterfaceError("Non-scalar value passed to set()")
    return self

  def where(self, *args, **kwargs):
    for entry in args:
      if isinstance(entry, (list, tuple)):
        # user has provided entry in the form
        # ("UPPER(`name`) = %s", topic.name)
        self._wheres.append(entry[0])
        if isinstance(entry[1], (list, tuple)):
          self._params.extend(entry[1])
        else:
          self._params.extend([entry[1]])
      else:
        # user has provided entry in the form
        # "UPPER(name) = 'MYNAME'"
        self._wheres.append(entry)
    for field, value in kwargs.items():
      if isinstance(value, (basestring, int, float, long, bool)):
        # if scalar, assume it's a direct equals.
        self._wheres.append("".join([field, " = %s"]))
        self._params.extend([value])
      else:
        # if not scalar, assume it's an IN query.
        self._wheres.append("".join([field, " IN (", ",".join(["%s"] * len(value)), ")"]))
        self._params.extend(value)
    return self

  def values(self, values):
    # for INSERT INTO queries.
    for entry in values:
      self._values.append(["".join(["(", ",".join(["%s"] * len(entry)) , ")"])])
      self._params.extend(entry)
    return self

  def match(self, fields, query):
    # WHERE MATCH(fields) AGAINST(query IN BOOLEAN MODE)
    self._wheres.append("MATCH(" + ",".join(fields) + ") AGAINST(%s IN BOOLEAN MODE)")
    self._params.extend([query])
    return self

  def group(self, field):
    self._group = field if isinstance(field, list) else [field]
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

  def queryString(self):
    fields = ["*"] if not self._fields else self._fields

    queryList = [self._type]

    if self._type == "SELECT" or self._type == "DELETE":
      queryList.extend([",".join(fields), "FROM"])
    elif self._type == "INSERT":
      queryList.append("INTO")
    elif self._type == "UPDATE":
      pass
    queryList.extend([self._table, " ".join(self._joins)])

    if self._type == "INSERT":
      queryList.extend(["".join(["(", fields , ")"]), "".join(["VALUES", ",".join(self._values) if self._values else "()"])])
    elif self._type == "UPDATE":
      queryList.extend(["SET", ", ".join(self._sets)] if self._sets else "")
    queryList.extend([" ".join(["WHERE", "&&".join(self._wheres)]) if self._wheres else "", " ".join(["GROUP BY", ",".join(self._group)]) if self._group else "", " ".join(["ORDER BY", str(self._order)]) if self._order else "", "LIMIT %s, %s"])

    return " ".join(queryList)

  def query(self, newCursor=False):
    self._params.extend([int(self._start), int(self._limit)])
    try:
      if newCursor:
        cursor = self.conn.cursor()
      else:
        cursor = self.cursor
      cursor.execute(self.queryString(), self._params)
    except (AttributeError, MySQLdb.OperationalError):
      # lost connection. reconnect and re-query.
      if not self.connect():
        print "Unable to reconnect to MySQL."
        raise
      cursor = self.cursor
      cursor.execute(self.queryString(), self._params)
    self.clearParams()
    return cursor

  def update(self, newCursor=False):
    self._type = "UPDATE"
    return self.query(newCursor=newCursor)

  def delete(self, newCursor=False):
    self._type = "DELETE"
    return self.query(newCursor=newCursor)

  def insert(self, newCursor=False):
    self._type = "INSERT"

  def list(self, valField, newCursor=False):
    if not isinstance(valField, basestring):
      return False
    queryCursor = self.query(newCursor=newCursor)
    if not queryCursor:
      return False
    resultList = [result[valField] for result in queryCursor]
    if newCursor:
      self.resetCursor(cursor=queryCursor)
    else:
      self.resetCursor()
    return resultList

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
    if newCursor:
      self.resetCursor(cursor=queryCursor)
    else:
      self.resetCursor()
    return queryResults

  def firstRow(self, newCursor=False):
    queryCursor = self.limit(1).query(newCursor=newCursor)
    if not queryCursor:
      return False
    firstRow = queryCursor.fetchone()
    if newCursor:
      self.resetCursor(cursor=queryCursor)
    else:
      self.resetCursor()
    return firstRow

  def firstValue(self, newCursor=False):
    self._type = "SELECT"
    firstRow = self.limit(1).firstRow(newCursor=newCursor)
    if not firstRow:
      return False
    rowKeys = firstRow.keys()
    return firstRow[rowKeys[0]]

  def commit(self):
    self.conn.commit()
    return self

  def close(self):
    self.conn.close()
    self._conn = None
