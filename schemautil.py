"""Code for reading, writing, and representing the FQL schema and example data.
"""

__author__ = ['Ryan Barrett <mockfacebook@ryanb.org>']

import collections
import copy
import datetime
import json
import pprint
import re

FQL_SCHEMA_PY_FILE = 'fql_schema.py'
FQL_SCHEMA_SQL_FILE = 'fql_schema.sql'
FQL_DATA_PY_FILE = 'fql_data.py'
FQL_DATA_SQL_FILE = 'fql_data.sql'
GRAPH_SCHEMA_PY_FILE = 'graph_schema.py'
GRAPH_DATA_PY_FILE = 'graph_data.py'
GRAPH_DATA_SQL_FILE = 'graph_data.sql'

PY_HEADER = """\
# Do not edit! Generated automatically by mockfacebook.
# http://code.google.com/p/mockfacebook/
# %s
""" % datetime.datetime.now()
SQL_HEADER = PY_HEADER.replace('#', '--')

# TODO: other object types have aliases too?
# e.g. http://graph.facebook.com/FarmVille
ALIAS_FIELD = 'username'


def values_to_sqlite(input):
  """Serializes Python values into a comma separated SQLite value string.

  The returned string can be used in the VALUES(...) section of an INSERT
  statement.
  """
  output = []

  for val in input:
    if isinstance(val, bool):
      val = str(int(val))
    elif isinstance(val, basestring):
      # can't use json.dumps() because SQLite doesn't support backslash escapes.
      # also note that sqlite escapes 's by doubling them.
      val = "'%s'" % val.replace("'", "''").encode('utf8')
      # val = string_to_sqlite(val)
    elif val is None:
      val = 'NULL'
    else:
      val = json.dumps(val)

    output.append(val)

  return ',\n  '.join(output)


class PySqlFiles(object):
  """A mixin that stores data in a Python file and a SQL file.

  Subclasses must override to_sql() and py_attrs if they want SQL and Python
  file output, respectively.

  Attributes:
    py_file: string filename
    sql_file: string filename

  Class attributes:
    py_attrs: tuple of string attributes to store in the .py file
  """
  py_attrs = ()

  def __init__(self, py_file, sql_file=None):
    self.py_file = py_file
    self.sql_file = sql_file

  def to_sql(self):
    pass

  def write(self):
    with open(self.py_file, 'w') as f:
      print >> f, PY_HEADER
      data = dict((attr, getattr(self, attr)) for attr in self.py_attrs)
      pprint.pprint(data, f)
    self.wrote_message(self.py_file)

    if self.sql_file:
      with open(self.sql_file, 'w') as f:
        print >> f, SQL_HEADER
        print >> f, self.to_sql()
      self.wrote_message(self.sql_file)

  @classmethod
  def read(cls):
    """Factory method.
    """
    inst = cls()
    with open(inst.py_file) as f:
      for attr, val in eval(f.read()).items():
        setattr(inst, attr, val)
    return inst

  def wrote_message(self, filename):
    print 'Wrote %s to %s.' % (self.__class__.__name__, filename)


# A column in a table.
#
# Defined at the top level so that Column(...)'s in .py files can be eval'ed.
#
# Attributes:
#   name: string
#   fb_type: string FQL type
#   sqlite_type: string SQLite type
#   indexable: boolean
Column = collections.namedtuple(
  'Column', ('name', 'fb_type', 'sqlite_type', 'indexable'))


class Schema(PySqlFiles):
  """An FQL or Graph API schema.

  Attributes:
    tables: dict mapping string table name to tuple of Column
  """
  py_attrs = ('tables',)

  def __init__(self, *args, **kwargs):
    super(Schema, self).__init__(*args, **kwargs)
    self.tables = {}

  def get_column(self, table, column):
    """Looks up a column.
  
    Args:
      table: string
      column: string
  
    Returns: Column or None
    """
    # TODO: store schema columns in ordered-dict (python 2.7), then remove this.
    for col in self.tables[table]:
      if col.name == column:
        return col

  def to_sql(self):
    """Returns the SQL CREATE TABLE statements for this schema.
    """
    tables = []

    # order tables alphabetically
    for table, cols in sorted(self.tables.items()):
      cols_str = ',\n'.join('  %s %s' % (c.name, c.sqlite_type) for c in cols)
      tables.append("""
CREATE TABLE `%s` (
%s
);
""" % (table, cols_str))

    return ''.join(tables)

  def json_to_sqlite(self, object, table):
    """Serializes a JSON object into a comma separated SQLite value string.
  
    The order of the values will match the order of the columns in the schema.

    Args:
      object: decoded JSON dict
      table: string
  
    Returns: string
    """
    columns = self.tables[table]
    values = []
  
    for i, col in enumerate(columns):
      val = object.get(col.name, '')
      if isinstance(val, (list, dict)):
        # store composite types as JSON strings
        val = json.dumps(val)
      values.append(val)
  
    return values_to_sqlite(values)

  def sqlite_to_json(self, cursor, table):
    """Converts SQLite query results to JSON result objects.

    This is used in fql.py.
  
    Args:
      cursor: SQLite query cursor
      table: string
  
    Returns:
      list of dicts representing JSON result objects
    """
    colnames = [d[0] for d in cursor.description]
    columns = [self.get_column(table, name) for name in colnames]
    objects = []

    for row in cursor.fetchall():
      object = {}
      for colname, column, val in zip(colnames, columns, row):
        # by default, use the SQLite type
        object[colname] = val
        # ...except for a couple special cases
        if column:
          if val and not column.sqlite_type:
            # composite types are stored as JSON strings
            object[colname] = json.loads(val)
          elif column.fb_type == 'bool':
            object[colname] = bool(val)

      objects.append(object)

    return objects


class FqlSchema(Schema):
  """The FQL schema.
  """
  def __init__(self):
    super(FqlSchema, self).__init__(FQL_SCHEMA_PY_FILE, FQL_SCHEMA_SQL_FILE)


class GraphSchema(Schema):
  """The Graph API schema.

  Attributes:
    connections: dict mapping string table name to tuple of string connection
      names
  """
  py_attrs = ('tables', 'connections')
  connections = {}

  def __init__(self):
    super(GraphSchema, self).__init__(GRAPH_SCHEMA_PY_FILE)


# A collection of objects for a given FQL or Graph API table.
#
# Defined at the top level so that Data(...)'s in .py files can be eval'ed.
#
# Attributes:
#   query: FQL query or Graph API path used to fetch the data.
#   data: decoded JSON object (usually dict or list of dicts)
Data = collections.namedtuple('Data', ('table', 'query', 'data'))

# A single Graph API connection.
#
# Attributes:
#   table: table name
#   id: id of the source object of this connection
#   name: name of this connection
#   data: decoded JSON object (usually dict or list of dicts)
#   query (derived, read only): Graph API path used to fetch the data.
Connection = collections.namedtuple('Connection', ('table', 'id', 'name', 'data'))

@property
def _Connection_query(self):
  return '%s/%s' % (self.id, self.name)

Connection.query = _Connection_query


class Dataset(PySqlFiles):
  """A set of FQL or Graph API example data.

  Attributes:
    schema: Schema
    data: dict mapping string FQL table name or Graph API object id to Data
  """
  py_attrs = ('data',)

  def __init__(self, py_file, sql_file=None, schema=None):
    super(Dataset, self).__init__(py_file, sql_file)
    self.schema = schema
    self.data = {}
  
  
class FqlDataset(Dataset):
  """An FQL dataset.
  """
  def __init__(self, schema=None):
    super(FqlDataset, self).__init__(FQL_DATA_PY_FILE, FQL_DATA_SQL_FILE, schema)

  def to_sql(self):
    """Returns a string with the SQL INSERT statements for this data.
    """
    output = ['BEGIN TRANSACTION;\n']

    # order tables alphabetically
    for table, data in sorted(self.data.items()):
      output.append("""
-- %s
--
-- %s
""" % (table, data.query))

      columns_str = ', '.join('`%s`' % col.name
                              for col in self.schema.tables[table])
      for object in data.data:
        # order columns to match schema (which is the order in FQL docs)
        values_str = self.schema.json_to_sqlite(object, table)
        output.append("""\
INSERT INTO `%s` (
  %s
) VALUES (
  %s
);
""" % (table, columns_str, values_str))

    output.append('COMMIT;')
    return '\n'.join(output)


class GraphDataset(Dataset):
  """A Graph API dataset.

  Attributes:
    connections: list of (table name, Connection) tuples
  """
  py_attrs = ('data', 'connections')

  def __init__(self, schema=None):
    super(GraphDataset, self).__init__(GRAPH_DATA_PY_FILE, GRAPH_DATA_SQL_FILE,
                                       schema)
    self.connections = {}

  def to_sql(self):
    """Generate SQL INSERT statements for the Graph API tables.

    One insert per row in SQLite, unfortunately. Details:
    http://stackoverflow.com/questions/1609637/
    """
    output = ['BEGIN TRANSACTION;']

    # objects and aliases
    for data in self.data.values():
      id = data.data['id']
      alias = data.data.get(ALIAS_FIELD)
      output.append(self.make_insert('graph_objects',
                                     id, alias, json.dumps(data.data)))

    # connections
    for conn in self.connections.values():
      for object in conn.data['data']:
        output.append(self.make_insert('graph_connections',
                                       conn.id, conn.name, json.dumps(object)))

    output.append('COMMIT;')
    return '\n'.join(output)

  def make_insert(self, table, *values):
    """Generates an INSERT statement for the given table and column values.

    Args:
      table: string
      values: string column values

    Returns: string
    """
    return """INSERT INTO %s VALUES (\n  %s\n);""" % (
      table, values_to_sqlite(values))