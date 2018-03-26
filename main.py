import re

import jinja2
import aiohttp
import asyncio
import math

from lxml import etree, html

from aiohttp_jinja2 import render_template, setup
from wtforms import Form, StringField, IntegerField
from wtforms.validators import InputRequired, NumberRange
from aiohttp import web

routes = web.RouteTableDef()

limit = 40


class SearchForm(Form):
    text = StringField('Слово для поиска', [InputRequired()])
    posts = IntegerField('Кол-вот цитат для поиска',
                         [InputRequired(), NumberRange(min=100, max=10000)])


async def fetch(session, url, sem):
    async with sem, session.get(url) as response:
        if response.status != 200:
            response.raise_for_status()
        return await response.text()


async def fetch_all(session, urls):
    sem = asyncio.Semaphore(limit)
    results = await asyncio.gather(
        *[fetch(session, url, sem) for url in urls],
        return_exceptions=True
    )

    return results


async def main(posts, session):
    sem = asyncio.Semaphore(limit)
    html_data = await fetch(session, 'http://bash.im/', sem)
    doc = html.fromstring(html_data)
    index_page = doc.xpath("//input[@class='page'][1]")
    if not index_page:
        print('Error while parsing data, cannot find start index page')
        return
    else:
        index_page = int(index_page[0].value)
    if posts:
        urls = ("http://bash.im/index/%s" % (index_page - x)
                for x in range(1, posts + 1) if index_page - x > 0)
        return urls


async def get_all_data(session, posts, word):
    occurrence_count = 0
    quotes_count = 0
    urls = await main(posts, session)
    pages = await fetch_all(session, urls)
    for page in pages:
        if not isinstance(page, str):
            print('An error occured while parsing - %s' % page.message)
            continue
        doc = html.fromstring(page)
        quotes = doc.xpath("//div[@class='quote']/div[@class='text']")
        for quote in quotes:
            quotes_count += 1
            if quotes_count > posts:
                return occurrence_count
            words = re.findall(r'\w+', quote.text_content())
            words = [word.lower() for word in words]
            if word in words:
                occurrence_count += 1

    return occurrence_count


@routes.get('/')
def handle_get(request):
    form = SearchForm()
    return render_template('index.jinja2', request, {'form': form})


@routes.post('/')
async def handle_post(request):
    data = await request.post()
    form = SearchForm(data)
    if form.validate():
        posts = math.ceil(form.posts.data / 50)
        word = form.text.data.lower()
        async with aiohttp.ClientSession() as session:
            res = await get_all_data(session, posts, word)
            response = 'Success, count - %d' % res
    else:
        response = ''
    return render_template(
        'index.jinja2', request, {'form': form, 'result': response}
    )


if __name__ == '__main__':
    app = web.Application()
    setup(app, loader=jinja2.FileSystemLoader('templates'))
    app.router.add_routes(routes)
    web.run_app(app)
