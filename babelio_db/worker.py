#!/usr/bin/env python
# vim:fileencoding=latin-1:ts=4:sw=4:sta:et:sts=4:ai
from __future__ import (unicode_literals, division, absolute_import,
                        print_function)
import collections
import six
from six.moves import zip

__license__ = 'GPL v3'
__copyright__ = '2014, VdF>'
__docformat__ = 'restructuredtext'

import socket, re, datetime
import mechanize, urllib.request, urllib.parse, urllib.error
from threading import Thread
from lxml.html import fromstring, tostring

from calibre.ebooks.metadata.book.base import Metadata
from calibre.ebooks.metadata import check_isbn
from calibre.ebooks.metadata.sources.base import fixcase, fixauthors
from calibre.utils.cleantext import clean_ascii_chars
from calibre.utils.config import JSONConfig

BASE_URL = 'https://www.babelio.com'

############ lrp
import datetime
from bs4 import BeautifulSoup as BS
from threading import Thread
import lxml
import time

from calibre.ebooks.metadata.book.base import Metadata
from calibre.ebooks.metadata import check_isbn
from calibre.library.comments import sanitize_comments_html
from calibre.utils.cleantext import clean_ascii_chars
from calibre.utils.icu import lower

from calibre_plugins.babelio import ret_soup, verify_isbn
# from calibre_plugins.babelio import noosfere
############ lrp

class Worker(Thread):

    def __init__(self, url, result_queue, browser, log, relevance, plugin, timeout=20):
        Thread.__init__(self)
        self.daemon = True
        self.url, self.result_queue = url, result_queue
        self.log, self.timeout = log, timeout
        self.relevance, self.plugin = relevance, plugin
        self.browser = browser.clone_browser()
        self.cover_url = self.isbn = self.bbl_id = None
        self.who = "[worker "+str(relevance)+"]"
        self.browser.set_handle_equiv(True)
        self.browser.set_handle_gzip(True)
        self.browser.set_handle_redirect(True)
        self.browser.set_handle_referer(True)
        self.browser.set_handle_robots(False)

        debug = 1
        self.log.info("\nIn worker")
        if debug:
            self.log.info(self.who,"url            : ", self.url)
            self.log.info(self.who,"self.relevance : ", self.relevance)
            self.log.info(self.who,"self.plugin    : ", self.plugin)
            self.log.info(self.who,"plugin         : ", self.plugin)

    def run(self):
        '''
        this control the rest of the worker process
        '''
        try:
            self.get_details()
        except:
            self.log.exception('get_details failed for url: %r' % self.url)

    def get_details(self):
        '''
        sets details this code uploads url then calls parse_details
        '''
        start = time.time()
        self.log.info(self.who,"in get details(), start : ", start)

        debug = 1
        if debug: self.log.info(self.who,"\n in get_details")
        try:
            self.bbl_id = self.parse_bbl_id(self.url)
        except:
            self.log.exception("Erreur en cherchant l'id babelio dans : %r" % self.url)
            self.bbl_id = None

        self.log.info(self.who,"apres parse_bbl_id() ... : ", time.time() - start)

        try:
            self.log.info('Url Babelio: %r' % self.url)
            policy = mechanize.DefaultCookiePolicy(rfc2965=True)
            # cj = mechanize.LWPCookieJar(policy=policy)
            # self.browser.set_cookiejar(cj)
            raw = self.browser.open_novisit(self.url, timeout=self.timeout).read().strip()
        except Exception as e:
            if isinstance(getattr(e, 'getcode', None), collections.Callable) and e.getcode() == 404:
                self.log.error('URL invalide : %r' % self.url)
                return
            attr = getattr(e, 'args', [None])
            attr = attr if attr else [None]
            if isinstance(attr[0], socket.timeout):
                msg = 'D�lai d\'attente d�pass�. R�essayez.'.encode('latin-1')
                self.log.error(msg)
            else:
                msg = 'Impossible de lancer la requ�te : %r'.encode('latin-1') % self.url
                self.log.exception(msg)
            return

        self.log.info(self.who,"apres self.browser.open_novisit() ... : ", time.time() - start)

        # if debug:                                     # may be long
        #     soup = BS(raw, "html5lib")
        #     self.log.info(self.who,"get details raw prettyfied :\n", soup.prettify())
        raw = raw.decode('latin-1', errors='replace')

        if '<title>404 - ' in raw:
            self.log.error('URL invalide : %r' % self.url)
            return

        try:
            root = fromstring(clean_ascii_chars(raw))
        except:
            msg = 'Impossible de parcourir la page : %r' % self.url
            self.log.exception(msg)
            return
        self.parse_details(root)

        self.log.info(self.who,"apres fromstring() ... : ", time.time() - start)

    def parse_details(self, root):

        start = time.time()
        self.log.info(self.who,"in parse_details(), start : ", start)

        try:
            title = self.parse_title(root)
        except:
            self.log.exception('Erreur en cherchant le titre dans : %r' % self.url)
            title = None

        self.log.info(self.who,"apres parse_title() ... : ", time.time() - start)

        try:
            authors = self.parse_authors(root)
        except:
            self.log.info('Erreur en cherchant l\'auteur dans: %r' % self.url)
            authors = []

        self.log.info(self.who,"apres parse_authors() ... : ", time.time() - start)

        if not title or not authors :
            self.log.error('Impossible de trouver le titre/auteur dans %r' % self.url)
            self.log.error('Titre: %r Auteurs: %r' % (title, authors))
            # return

        mi = Metadata(title, authors)
        mi.set_identifier('babelio', self.bbl_id)
        try:
            isbn, publisher, pubdate = self.parse_meta(root)
            if isbn:
                self.isbn = mi.isbn = isbn
            if publisher:
                self.publisher = mi.publisher = publisher
            if pubdate :
                self.pubdate = mi.pubdate = pubdate
        except:
            self.log.exception('Erreur en cherchant ISBN, �diteur et date de publication dans : %r' % self.url)

        self.log.info(self.who,"apres parse_meta() ... : ", time.time() - start)

        try:
            mi.rating = self.parse_rating(root)
        except:
            self.log.exception('Erreur en cherchant la note dans : %r' % self.url)

        self.log.info(self.who,"apres parse_rating() ... : ", time.time() - start)

        try:
            mi.comments = self.parse_comments(root).replace('\r\n', '').replace('\r', '').strip()
            if mi.comments == '' :
                self.log.info('Pas de commentaires pour ce livre')
        except:
            self.log.exception('Erreur en cherchant le r�sum� : %r' % self.url)

        self.log.info(self.who,"apres parse_comments() ... : ", time.time() - start)

        if JSONConfig('plugins/Babelio').get('cover', False) == True:
            try:
                self.cover_url = self.parse_cover(root)
            except:
                self.log.exception('Erreur en cherchant la couverture dans : %r' % self.url)

        else :
            self.log.info('T�l�chargement de la couverture d�sactiv�')
            self.cover_url = None
        mi.has_cover = bool(self.cover_url)

        self.log.info(self.who,"apres parse_cover() ... : ", time.time() - start)

        try:
            tags = self.parse_tags(root)
            if tags:
                mi.tags = tags
        except:
            self.log.exception('Erreur en cherchant les �tiquettes dans : %r' % self.url)

        self.log.info(self.who,"apres parse_tags() ... : ", time.time() - start)

        if self.bbl_id:
            if self.isbn:
                self.plugin.cache_isbn_to_identifier(self.isbn, self.bbl_id)
            if self.cover_url:
                self.plugin.cache_identifier_to_cover_url(self.bbl_id, self.cover_url)
        mi.language = 'fr'
        mi.authors = fixauthors(mi.authors)
        mi.tags = list(map(fixcase, mi.tags))
        mi.isbn = check_isbn(mi.isbn)
        self.result_queue.put(mi)

    def parse_bbl_id(self, url):
        '''
        returns either None or a valid bbl_id
        '''
        bbl_id = ""
        if "https://www.babelio.com/livres/" in url:
            bbl_id = url.replace("https://www.babelio.com/livres/","").strip()
        if "/" in bbl_id and bbl_id.split("/")[-1].isnumeric():
            return bbl_id
        else:
            return None

        return re.search(r'/(\d+)', url).groups(0)[0]

    def parse_title(self, root):
        title_node = root.xpath("//div [@class='livre_header_con']/h1/a")
        if not title_node:
            return None
        title_text = title_node[0].text_content().strip()
        return title_text

    def parse_authors(self, root):
        node_authors = root.xpath(".//*[@id='page_corps']/div/div[3]/div[2]/div[1]/div[2]/span[1]/a/span")
        if not node_authors:
            return
        authors_html = tostring(node_authors[0], method='text', encoding='unicode').replace('\n', '').strip()
        authors = []
        for a in authors_html.split(','):
            authors.append(a.strip())
        return authors

    def parse_rating(self, root):
        #rating_node = root.xpath(".//*[@id='page_corps']/div/div[3]/div[2]/div[1]/div[2]/span[2]/span[1]")
        rating_node = root.xpath('//span[@itemprop="aggregateRating"]/span[@itemprop="ratingValue"]')
        if rating_node:
            rating_text = tostring(rating_node[0], method='text', encoding=str)
            rating_text = rating_text.replace('/', '')
            self.log.info('rating :', eval(rating_text))
            rating_value = float(rating_text) / 5 * 100
            if rating_value >= 100:
                return rating_value / 100
            return eval(rating_text)

    def parse_comments(self, root):
        description_node = root.xpath('//div [@id="d_bio"]/span/a')
        if description_node:
            java = description_node[0].get('onclick')
            hash_url = re.search(r',([0-9]+?),([0-9]*)\)', java)
            comment_url = BASE_URL + '/aj_voir_plus_a.php'
            data = urllib.parse.urlencode({'type':hash_url.group(1), 'id_obj':hash_url.group(2) })
            req = mechanize.Request(comment_url, data)
            req.add_header('X-Requested-With', 'XMLHttpRequest')
            req.add_header('Referer', self.url)
            req.add_header('Host', 'www.babelio.com')
            req.add_header('Connection', 'Keep-Alive')
            req.add_header('Content-Type', 'application/x-www-form-urlencoded; charset=UTF-8')
            req.add_header('Accept', '*/*')
            handle = self.browser.open_novisit(req)
            comments = handle.read()
            return comments.replace(b'\x92', b'\x27').replace(b'\x19', b'\x27').replace(b'\x9C', b'\x6f\x65').decode('latin-1', errors='replace')
        else :
            comments = ''
            if root.xpath('//div [@id="d_bio"]') :
                comments = tostring(root.xpath('//div [@id="d_bio"]')[0], method='text', encoding=str)
            return comments

    def parse_cover(self, root):
        start = time.time()
        imgcol_node = root.xpath(".//*[@id='page_corps']/div/div[3]/div[2]/div[1]/div[1]/img")
        self.log.info(self.who,"in parse_cover 0 : ", time.time() - start)
        if imgcol_node:
            url = imgcol_node[0].get('src')
            img_url = BASE_URL + url
            self.log.info(self.who,"in parse_cover 1 : ", time.time() - start)
            if url.startswith('http'):
                img_url = url
                self.log.info(self.who,"in parse_cover 2 : ", time.time() - start)
            self.log.info('img_url :', img_url)
          # the following takes forever (amazon site?), let's decide url is correct.
          # anyway when fetching cover this will be accessed in time (or not)
            # try :
            #     info = self.browser.open_novisit(img_url, timeout=self.timeout).info()
            #     self.log.info(self.who,"in parse_cover 3 : ", time.time() - start)
            # except :
            #     self.log.warning('Lien pour l\'image invalide : %s' % img_url)
            #     return None
            # #if int(info.getheader('Content-Length')) > 1000:
            # if int(info.get('Content-Length')) > 1000:
            #     self.log.info(self.who,"in parse_cover 4 : ", time.time() - start)
            return img_url
            # else:
            #     self.log.warning('Lien pour l\'image invalide : %s' % img_url)

    def parse_meta(self, root):
        meta_node = root.xpath(".//*[@id='page_corps']/div/div[3]/div[2]/div[1]/div[2]/div[1]")
        if meta_node:
            publisher_re = isbn_re = pubdate_re = publication = None
            meta_text = tostring(meta_node[0], method='text', encoding=str).strip()
            if re.search(r'(?<=teur : )([^\n(]*)', meta_text):
                publisher_re = re.search(r'(?<=teur : )([^\n(]*)', meta_text).group(0)
            if re.search(r'(?<=[BN|bn] : )([^\n]*)', meta_text) :
                isbn_re = re.search(r'(?<=[BN|bn] : )([^\n(]*)', meta_text).group(0)
            if re.search(r'\(([0-9]{4})\)', meta_text):
                pubdate_re = re.search(r'\(([0-9]{4})\)', meta_text).group(1)
                publication = self._convert_date_text(pubdate_re)
            # meta_re = re.search(r'.*?\s?:\s?(\w*)\s*\n?.*?\s?:\s?([^\n]*)\n?\(([0-9]{4})\)', meta_text)
            # self.log.info(isbn_re, '  ', publisher_re, '  ', pubdate_re)
            return isbn_re, publisher_re, publication


    def parse_tags(self, root):
        tags_node = root.xpath('//p[@class="tags"]/a[@rel="tag"]')
        if tags_node:
            tags_list = list()
            for tag in tags_node:
                texttag = tag.text.replace('\ufffd', "'")
                tags_list.append(texttag)
            if len(tags_list) > 0:
                return tags_list

    def _convert_date_text(self, date_text):
        year = int(date_text[-4:])
        month = 1
        day = 1
        if len(date_text) > 4:
            text_parts = date_text[:len(date_text) - 5].partition(' ')
            month_name = text_parts[0]
            month_dict = {"janvier":1, "f�vrier":2, "mars":3, "avril":4, "mai":5, "juin":6,
                "juillet":7, "ao�t":8, "Septembre":9, "octobre":10, "novembre":11, "d�cembre":12}
            month = month_dict.get(month_name, 2)
            if len(text_parts[2]) > 0:
                day = int(re.match('([0-9]+)', text_parts[2]).groups(0)[0])
        from calibre.utils.date import utc_tz
        return datetime.datetime(year, month, day, tzinfo=utc_tz)
