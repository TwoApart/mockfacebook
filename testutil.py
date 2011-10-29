"""Unit test utilities.

TODO: put a utility in server that combines all routes, then use that in all tests
"""

__author__ = ['Ryan Barrett <mockfacebook@ryanb.org>']

import cStringIO
import json
import re
import sqlite3
import sys
import unittest
import urllib

import webapp2

import schemautil
import server

# The me() user id in the publishable example data used for testing.
ME = 212038


def make_test_db(filename):
  """Returns a SQLite db connection with the FQL schema and example data.

  Args:
    filename: the SQLite database file.
  """
  conn = sqlite3.connect(filename)

  for file in ('mockfacebook.sql', schemautil.FQL_SCHEMA_SQL_FILE,
               schemautil.FQL_DATA_SQL_FILE, schemautil.GRAPH_DATA_SQL_FILE):
    with open(file) as f:
      conn.executescript(f.read())

  return conn


class HandlerTest(unittest.TestCase):
  """Base test class for webapp2 request handlers.
  """

  conn = None

  def setUp(self, *handler_classes):
    """Args:
    handler_classes: RequestHandlers to initialize
    """
    super(HandlerTest, self).setUp()
    if HandlerTest.conn is None:
      HandlerTest.conn = make_test_db(':memory:')

    for cls in handler_classes:
      cls.init(self.conn, ME)

    self.app = server.application()

  def expect(self, path, expected, args=None):
    """Makes a request and checks the response.

    Args:
      path: string
      expected: if string, the expected response body. if list or dict,
        the expected JSON response contents.
      kwargs: passed to get_response()
    """
    response = None
    try:
      response = self.get_response(path, args=args)
      self.assertEquals(200, response.status_int)
      response = response.body
      if isinstance(expected, basestring):
        self.assertEquals(expected, response)
      else:
        results = json.loads(response)
        if not isinstance(expected, list):
          expected = [expected]
          results = [results]
        self.assertEquals(len(expected), len(results), `expected, results`)
        for e, r in zip(expected, results):
          self.assert_dict_equals(e, r)
    except:
      print >> sys.stderr, '\nquery: %s' % path
      print >> sys.stderr, 'expected: %r' % expected
      print >> sys.stderr, 'received: %r' % response
      raise

  def get_response(self, path, args=None):
    if args:
      path = '%s?%s' % (path, urllib.urlencode(args))
    return self.app.get_response(path)

  def assert_dict_equals(self, expected, actual):
    msgs = []

    for key in set(expected.keys()) | set(actual.keys()):
      e = expected.get(key, None)
      a = actual.get(key, None)
      if isinstance(e, re._pattern_type):
        if not re.match(e, a):
          msgs.append("%s: %r doesn't match %s" % (key, e, a))
      elif isinstance(e, dict) and isinstance(a, dict):
        self.assert_dict_equals(e, a)
      # this is only here because we don't exactly match FB in whether we return
      # or omit some "empty" values, e.g. 0, null, ''. see the TODO in graph_on_fql.py.
      elif not e and not a:
        continue
      elif e != a:
        msgs.append('%s: %r != %r' % (key, e, a))

    if msgs:
      self.fail('\n'.join(msgs))