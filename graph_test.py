#!/usr/bin/python
"""Unit tests for graph.py.
"""

__author__ = ['Ryan Barrett <mockfacebook@ryanb.org>']

import re
import traceback
import unittest

import graph
import schemautil
import testutil


class TestBase(testutil.HandlerTest):

  dataset = testutil.maybe_read(schemautil.GraphDataset)

  def setUp(self, *args):
    super(TestBase, self).setUp(*args)
    self.alice = {'id': '1', 'foo': 'bar'}
    self.bob = {'id': '2', 'inner': {'foo': 'baz'}}
    self.alice_albums = {'data': [{'id': '3'}, {'id': '4'}]}
    self.bob_albums = {'data': [{'id': '5'}]}

    self.conn.executescript("""
INSERT INTO graph_objects VALUES('1', 'alice', '{"id": "1", "foo": "bar"}');
INSERT INTO graph_objects VALUES('2', 'bob', '{"id": "2", "inner": {"foo": "baz"}}');
INSERT INTO graph_connections VALUES('1', 'albums', '{"id": "3"}');
INSERT INTO graph_connections VALUES('1', 'albums', '{"id": "4"}');
INSERT INTO graph_connections VALUES('2', 'albums', '{"id": "5"}');
INSERT INTO graph_connections VALUES('1', 'picture', '"http://alice/picture"');
INSERT INTO graph_connections VALUES('2', 'picture', '"http://bob/picture"');
""")
    self.conn.commit()

  def _test_example_data(self, data):
    """Args:
      data: list of Data or Connection with url paths and expected results
    """
    self.conn.executescript(self.dataset.to_sql())
    self.conn.commit()
    graph.ObjectHandler.me = self.dataset.data['me'].data['id']
    for datum in data:
      self.expect('/%s' % datum.query, datum.data)

  def expect_redirect(self, path, redirect_to):
    resp = self.get_response(path)
    self.assertEquals(302, resp.status_int)
    self.assertEquals(redirect_to, resp.headers['Location'])

  def expect_error(self, path, exception):
    """Args:
      path: string
      exception: expected instance of a GraphError subclass
    """
    self.expect(path, exception.message, expected_status=exception.status)


class ObjectTest(TestBase):

  def setUp(self):
    super(ObjectTest, self).setUp(graph.ObjectHandler)

  def test_example_data(self):
    if self.dataset:
      self._test_example_data(self.dataset.data.values())

  def test_id(self):
    self.expect('/1', self.alice)

  def test_alias(self):
    self.expect('/alice', self.alice)

  def test_me(self):
    self.expect('/me', self.alice)

  def test_not_found(self):
    self.expect_error('/9', graph.ObjectNotFoundError())

  def test_single_ids_not_found(self):
    self.expect_error('/?ids=9', graph.ObjectsNotFoundError())

  def test_multiple_ids_not_found(self):
    self.expect_error('/?ids=9,8', graph.ObjectsNotFoundError())

  def test_alias_not_found(self):
    for bad_query in '/foo', '/?ids=foo', '/?ids=alice,foo':
      self.expect_error(bad_query, graph.AliasNotFoundError('foo'))

    self.expect_error('/?ids=foo,bar', graph.AliasNotFoundError('foo,bar'))

  def test_id_already_specified(self):
    self.expect_error('/foo?ids=bar', graph.IdSpecifiedError('foo'))

  def test_empty_identifier(self):
    for bad_query in '/?ids=', '/?ids=alice,', '/?ids=alice,,2':
      self.expect_error(bad_query, graph.EmptyIdentifierError())

  def test_ids_query_param(self):
    self.expect('/?ids=alice,bob',
                {'alice': self.alice, 'bob': self.bob})
    self.expect('/?ids=bob,1',
                {'1': self.alice, 'bob': self.bob})

  def test_ids_always_prefers_alias(self):
    self.expect('/?ids=alice,1', {'alice': self.alice})
    self.expect('/?ids=1,alice', {'alice': self.alice})


class ConnectionTest(TestBase):

  def setUp(self):
    super(ConnectionTest, self).setUp(graph.ConnectionHandler)

  def test_example_data(self):
    if self.dataset:
      self._test_example_data(conn for conn in self.dataset.connections.values()
                              if conn.name != graph.REDIRECT_CONNECTION)

  def test_id(self):
    self.expect('/1/albums', self.alice_albums)

  def test_alias(self):
    self.expect('/alice/albums', self.alice_albums)

  def test_me(self):
    self.expect('/me/albums', self.alice_albums)

  def test_id_not_found(self):
    self.expect('/9/albums', 'false')

  def test_alias_not_found(self):
    self.expect_error('/foo/albums', graph.AliasNotFoundError('foo'))

  def test_connection_not_found(self):
    self.expect_error('/alice/foo', graph.UnknownPathError('foo'))

  def test_no_connection_data(self):
    self.expect('/alice/family', {'data': []})
    self.expect('//family?ids=alice', {'alice': {'data': []}})

  def test_ids_query_param(self):
    self.expect('//albums?ids=alice,bob',
                {'alice': self.alice_albums, 'bob': self.bob_albums})

  def test_picture_redirect(self):
    for path in ('/alice/picture',
                 '//picture?ids=alice',
                 '//picture?ids=alice,bob'):
      expected = 'http://alice/picture'
      self.expect_redirect(path, expected)


if __name__ == '__main__':
  unittest.main()
