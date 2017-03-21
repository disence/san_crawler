import tornado.web
import tornado.ioloop
import redis
import os

if __name__ == '__main__':

    class QueryHandler(tornado.web.RequestHandler):
        def set_default_headers(self):
            self.set_header("Access-Control-Allow-Origin", "*")

        def get(self, wwpn):
            wwpn = wwpn.lower()
            result = r.hgetall(wwpn) or {}
            self.write(result)

    class ListHandler(tornado.web.RequestHandler):
        def set_default_headers(self):
            self.set_header("Access-Control-Allow-Origin", "*")

        def get(self, pattern):
            self.write(
                {
                    'wwpn_list':r.keys("*{}*".format(pattern.lower()))
                }
            )

    def make_app():
        return tornado.web.Application([
            (r"/wwpn/(\w{2}(?::\w{2}){7})", QueryHandler),
            (r"/list/([:0-9a-zA-Z]+)", ListHandler),
        ])

    if __name__ == "__main__":
        r = redis.StrictRedis(
            host='redis',
            port=6379,
            decode_responses=True,
            db=0
        )

        app = make_app()
        app.listen(8888)
        tornado.ioloop.IOLoop.current().start()
