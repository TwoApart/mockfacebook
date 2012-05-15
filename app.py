import webapp2
import json


class TestUsersHandler(webapp2.RequestHandler):
    ROUTES = [
        (r'/(\d+)/accounts/test-users', 'app.TestUsersHandler'),
    ]

    @classmethod
    def init(cls, conn, me):
        """
          conn: sqlite3.Connection
        """
        print "INIT"
        cls.conn = conn

    def get(self, app_id):
        sql = """
            SELECT DISTINCT user_id, token
            FROM oauth_access_tokens;
        """
        cursor = self.conn.execute(sql)
        rows = cursor.fetchall()

        results = {'data': []}
        for row in rows:
            user_id, token = row
            results['data'].append({'id': user_id, 'access_token': token})

        self.response.headers['Content-Type'] = 'text/plain; charset=utf-8'
        json.dump(results, self.response.out, indent=2)
