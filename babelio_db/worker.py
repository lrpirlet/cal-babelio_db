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

class Worker(Thread):

    def __init__(self, url, result_queue, browser, log, relevance, plugin, timeout=20):
        Thread.__init__(self)
        self.daemon = True
        self.url, self.result_queue = url, result_queue
        self.log, self.timeout = log, timeout
        self.relevance, self.plugin = relevance, plugin
        self.browser = browser.clone_browser()
        self.cover_url = self.isbn = self.bab_id = None
        self.browser.set_handle_equiv(True)
        self.browser.set_handle_gzip(True)
        self.browser.set_handle_redirect(True)
        self.browser.set_handle_referer(True)
        self.browser.set_handle_robots(False)

    def run(self):
        try:
            self.get_details()
        except:
            self.log.exception('get_details failed for url: %r' % self.url)

    def get_details(self):
        try:
            self.bab_id = self.parse_bab_id(self.url)
        except:
            self.log.exception('Erreur en cherchant l\'id babelio dans : %r' % self.url)
            self.bab_id = None
        try:
            self.log.info('Url Babelio: %r' % self.url)
            policy = mechanize.DefaultCookiePolicy(rfc2965=True)
            cj = mechanize.LWPCookieJar(policy=policy)
            self.browser.set_cookiejar(cj)
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

    def parse_details(self, root):
        try:
            title = self.parse_title(root)
        except:
            self.log.exception('Erreur en cherchant le titre dans : %r' % self.url)
            title = None

        try:
            authors = self.parse_authors(root)
        except:
            self.log.info('Erreur en cherchant l\'auteur dans: %r' % self.url)
            authors = []

        if not title or not authors :
            self.log.error('Impossible de trouver le titre/auteur dans %r' % self.url)
            self.log.error('Titre: %r Auteurs: %r' % (title, authors))
            # return

        mi = Metadata(title, authors)
        mi.set_identifier('babelio', self.bab_id)
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

        try:
            mi.rating = self.parse_rating(root)
        except:
            self.log.exception('Erreur en cherchant la note dans : %r' % self.url)

        try:
            mi.comments = self.parse_comments(root).replace('\r\n', '').replace('\r', '').strip()
            if mi.comments == '' :
                self.log.info('Pas de commentaires pour ce livre')
        except:
            self.log.exception('Erreur en cherchant le r�sum� : %r' % self.url)

        if JSONConfig('plugins/Babelio').get('cover', False) == True:
            try:
                self.cover_url = self.parse_cover(root)
            except:
                self.log.exception('Erreur en cherchant la couverture dans : %r' % self.url)

        else :
            self.log.info('T�l�chargement de la couverture d�sactiv�')
            self.cover_url = None
        mi.has_cover = bool(self.cover_url)

        try:
            tags = self.parse_tags(root)
            if tags:
                mi.tags = tags
        except:
            self.log.exception('Erreur en cherchant les �tiquettes dans : %r' % self.url)
        if self.bab_id:
            if self.isbn:
                self.plugin.cache_isbn_to_identifier(self.isbn, self.bab_id)
            if self.cover_url:
                self.plugin.cache_identifier_to_cover_url(self.bab_id, self.cover_url)
        mi.language = 'fr'
        mi.authors = fixauthors(mi.authors)
        mi.tags = list(map(fixcase, mi.tags))
        mi.isbn = check_isbn(mi.isbn)
        self.result_queue.put(mi)

    def parse_bab_id(self, url):
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
        imgcol_node = root.xpath(".//*[@id='page_corps']/div/div[3]/div[2]/div[1]/div[1]/img")
        if imgcol_node:
            url = imgcol_node[0].get('src')
            img_url = BASE_URL + url
            if url.startswith('http'):
                img_url = url
            self.log.info('img_url :', img_url)
            try :
                info = self.browser.open_novisit(img_url, timeout=self.timeout).info()
            except :
                self.log.warning('Lien pour l\'image invalide : %s' % img_url)
                return None
            #if int(info.getheader('Content-Length')) > 1000:
            if int(info.get('Content-Length')) > 1000:
                return img_url
            else:
                self.log.warning('Lien pour l\'image invalide : %s' % img_url)

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
