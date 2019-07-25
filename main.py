import asyncio
import concurrent
import sys
import re
from html.parser import HTMLParser
import aiohttp
import async_timeout

PORT = int(sys.argv[1])
LISTEN_ADDR_IPV4 = "0.0.0.0"
FETCH_TIMEOUT = 5

PATH_RE = re.compile('GET\s(.+)\sHTTP')
SCRIPT_RE = re.compile('<(script|noscript)(.|\n)*?script>')
SIX_SIGNS_RE = re.compile('\s(\w{6})\s')


class MLStripper(HTMLParser):
    def __init__(self):
        self.reset()
        self.strict = False
        self.convert_charrefs= True
        self.fed = []

    def handle_data(self, d):
        self.fed.append(d)

    def get_data(self):
        return ''.join(self.fed)


def strip_tags(html):
    s = MLStripper()
    s.feed(html)
    return s.get_data()


def find_words(html):
    html_wo_scripts = SCRIPT_RE.sub('', html)
    words = strip_tags(html_wo_scripts)
    for sign in '.,\/#!$%\^&\*;:{}=\-_`~()]\n':
        words = words.replace(sign, ' ')
    words_arr = SIX_SIGNS_RE.findall(words)
    return words_arr



async def fetch(session, url):
    with async_timeout.timeout(FETCH_TIMEOUT):
        async with session.get(url) as response:
            return await response.content.read()


async def handle_connection(reader, writer):
    peername = writer.get_extra_info('peername')
    async with aiohttp.ClientSession() as session:
        print('Accepted connection from {}'.format(peername))
        request_data = b''
        path = '/'
        while not reader.at_eof():
            try:
                request_data = await asyncio.wait_for(reader.readline(), timeout=10.0)
                print(request_data.decode('utf-8'))
                path_arr = PATH_RE.findall(request_data.decode('utf-8'))
                if len(path_arr):
                    path = path_arr[0]
            except concurrent.futures.TimeoutError:
                break

        print(path)
        habr_response = await fetch(session, 'https://habr.com{}'.format(path))

        response_body_raw = habr_response.decode('utf-8', errors='ignore')
        for word in find_words(response_body_raw):
            response_body_raw = response_body_raw.replace(word, '{} &trade;'.format(word))

        response_body_raw = response_body_raw.replace('https://habr.com', 'http://{}:3333'.format(peername[0]))

        response_headers = {
            'HTTP/1.1': '200 OK',
            'Content-Type': 'text/html; charset=UTF-8',
            'Content-Length': len(response_body_raw),
            'Connection': 'close',
        }
        response_headers_raw = '\n'.join('{}: {}'.format(k, v) for k, v in response_headers.items())
        writer.write('\n{}\n'.format(response_headers_raw).encode('utf-8'))
        writer.write(response_body_raw.encode('utf-8'))
        writer.close()


def main():
    loop = asyncio.get_event_loop()
    task_v4 = asyncio.start_server(
        handle_connection,
        LISTEN_ADDR_IPV4,
        PORT,
        reuse_port=True,
        loop=loop
    )

    server = loop.run_until_complete(task_v4)
    print('Serving on {}'.format(server.sockets[0].getsockname()))
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    loop.close()


if __name__ == "__main__":
    main()
