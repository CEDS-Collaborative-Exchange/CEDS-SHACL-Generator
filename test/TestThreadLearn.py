import concurrent.futures
import urllib.request
import unittest



class MyTestCase(unittest.TestCase):
    URLS = ['http://www.foxnews.com/',
            'http://www.cnn.com/',
            'http://europe.wsj.com/',
            'http://www.bbc.co.uk/',
            'http://nonexistent-subdomain.python.org/']

    # Retrieve a single page and report the URL and contents
    def load_url(url, timeout):
        with urllib.request.urlopen(url, timeout=timeout) as conn:
            return conn.read()



    def test_something(self):
        # We can use a with statement to ensure threads are cleaned up promptly
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            # Start the load operations and mark each future with its URL

            # future_to_url = {
            #     executor.submit(self.load_url, urlk, 60): urlk for urlk in self.URLS
            # }
            future_to_url = {}
            for url in self.URLS:
                future_to_url.setdefault(executor.submit(self.load_url, url, 60),url)

            #objType =type(future_to_url)
            print("type of keys%s",future_to_url.values())

            for future in concurrent.futures.as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    data = future.result()
                except Exception as exc:
                    print('%r generated an exception: %s' % (url, exc))
                else:
                    print('%r page is %d bytes' % (url, len(data)))


if __name__ == '__main__':
    unittest.main()
