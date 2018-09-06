import tornado.web
import tornado.ioloop
import os
import pymongo

mongo = {
    "host": "mongo",
    "port": 27017,
    "db": "wwpn_info",
    "collection": "locations"
}

if __name__ == '__main__':

    class QueryHandler(tornado.web.RequestHandler):
        def set_default_headers(self):
            self.set_header("Access-Control-Allow-Origin", "*")

        def get(self, wwpn):
            wwpn = wwpn.lower()
            query_result = collection.find_one({"wwpn": wwpn}, {"_id": 0}) or {}
            self.write(query_result)

    class ListHandler(tornado.web.RequestHandler):
        def set_default_headers(self):
            self.set_header("Access-Control-Allow-Origin", "*")

        def get(self, pattern):
            query_result = collection.find(
                {"wwpn": {'$regex': f'.*{pattern}.*'}},
                {"wwpn": 1, "_id": 0}
            )
            self.write(
                {
                    'wwpn_list': list(map(lambda x: x["wwpn"], query_result))
                }
            )

    def make_app():
        return tornado.web.Application([
            (r"/wwpn/(\w{2}(?::\w{2}){7})", QueryHandler),
            (r"/list/([:0-9a-zA-Z]+)", ListHandler),
        ])

    if __name__ == "__main__":
        client = pymongo.MongoClient(mongo["host"], mongo["port"])
        db = client[mongo["db"]]
        collection = db[mongo["collection"]]

        app = make_app()
        app.listen(8888)
        tornado.ioloop.IOLoop.current().start()
