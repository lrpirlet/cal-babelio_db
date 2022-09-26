#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai
'''
# to mix UTF-8 (in __init__.py) and latin-& (in worker.py) just confuses me completely
# delme vim:fileencoding=latin-1:ts=4:sw=4:sta:et:sts=4:ai
'''
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
# from calibre.utils.config import JSONConfig

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
    '''
    worker is a thread that runs in parallel with other worker...
    In order to distinguish activities from worker's each log activity will contain who (see definition below)
    worker will queue (result_queue) all gathered meta-data about the book submited (url)
    '''

    def __init__(self, url, result_queue, browser, log, relevance, plugin, dbg_lvl, timeout=20):
        Thread.__init__(self)
        self.daemon = True
        self.url = url
        self.result_queue = result_queue
        self.log = log
        self.timeout = timeout
        self.relevance = relevance
        self.plugin = plugin
        self.browser = browser.clone_browser()
        self.br = browser.clone_browser()
        self.dbg_lvl = dbg_lvl
        self.with_cover = self.plugin.with_cover

        self.cover_url = self.isbn = self.bbl_id = None
        self.who = "[worker "+str(relevance)+"]"
        self.browser.set_handle_equiv(True)
        self.browser.set_handle_gzip(True)
        self.browser.set_handle_redirect(True)
        self.browser.set_handle_referer(True)
        self.browser.set_handle_robots(False)

        self.debug=self.dbg_lvl & 2
        self.debugt=self.dbg_lvl & 8
        self.log.info(self.who,"In worker\n")
        if self.debug:
            self.log.info(self.who,"self.url            : ", self.url)
            self.log.info(self.who,"self.relevance      : ", self.relevance)
            self.log.info(self.who,"self.plugin         : ", self.plugin)
            self.log.info(self.who,"self.dbg_lvl        : ", self.dbg_lvl)
            self.log.info(self.who,"self.timeout        : ", self.timeout)
            self.log.info(self.who,"self.with_cover     : ", self.with_cover)


    def run(self):
        '''
        this control the rest of the worker process
        '''
        self.log.info(self.who,"in run(self)\n")

        try:
            self.get_details()
        except:
            self.log.exception('get_details failed for url: %r' % self.url)

    def get_details(self):
        '''
        sets details this code uploads url then calls parse_details
        '''
        self.log.info(self.who,"in get_details(self)\n")
        if self.debugt:
            start = time.time()
            self.log.info(self.who,"in get details(), start time : ", start)
        if self.debug:
            self.log.info(self.who,"calling ret_soup(log, dbg_lvl, br, url, rkt=None, who='[__init__]')")
            self.log.info(self.who,"self.url : ", self.url)
            self.log.info(self.who,"who      : ", self.who)

      # get the babelio page content and the true url
        rsp = ret_soup(self.log, self.dbg_lvl, self.br, self.url, who=self.who)
        soup = rsp[0]
        url_vrai = rsp[1]

      # find the babelio id
        try:
            # self.bbl_id = self.parse_bbl_id(self.url)
            self.bbl_id = self.parse_bbl_id(url_vrai)
        except:
            # self.log.exception("Erreur en cherchant l'id babelio dans : %r" % self.url)
            self.log.exception("Erreur en cherchant l'id babelio dans : %r" % url_vrai)
            self.bbl_id = None

        if self.debugt:
            self.log.info(self.who,"Temps après parse_bbl_id() ... : ", time.time() - start)

      # get the babelio page content
        try:
            self.log.info('Url Babelio: %r' % self.url)
            # policy = mechanize.DefaultCookiePolicy(rfc2965=True)
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
                msg = 'Délai d\'attente dépassé. Réessayez.'
                self.log.error(msg)
            else:
                msg = 'Impossible de lancer la requête : %r' % self.url
                self.log.exception(msg)
            return

      # edit raw
        raw = raw.decode('latin-1', errors='replace')

      # handle internet return status
        if '<title>404 - ' in raw:
            self.log.error('URL invalide : %r' % self.url)
            return

        if self.debugt:
            self.log.info(self.who,"Temps après self.browser.open_novisit() ... : ", time.time() - start)

        if self.debug:                                     # may be very long
            # effect of raw being decoded to latin_1 inside calibre...
        #    rawbs=BS(raw, "html5lib")   (raw = raw.decode('latin-1', errors='replace') )
        #    self.log.info(self.who,"get details rawbs prettyfied :\n", rawbs.prettify())
            # resultat (court extrait...)
            # Poussé par lamour dune jolie femme, il simprovisera un moment professeur dans une école
        #    self.log.info(self.who,"get details soup prettyfied :\n", soup.prettify())
            # resultat (court extrait...)
            # Poussé par l’amour d’une jolie femme, il s’improvisera un moment professeur dans une école
            pass


        try:
            root = fromstring(clean_ascii_chars(raw))
        except:
            msg = 'Impossible de parcourir la page : %r' % self.url
            self.log.exception(msg)
            return
        self.parse_details(root, soup)

        if self.debugt:
            self.log.info(self.who,"Temps après fromstring() ... : ", time.time() - start)

    def parse_details(self, root, soup):
        '''
        gathers all details needed to complete the calibre metadata, handels
        errors and sets mi
        '''
        self.log.info(self.who,"in parse_details(self, root)\n")
        if self.debug:
            self.log.info(self.who,"type(root) : ", type(root))
        if self.debugt:
            start = time.time()
            self.log.info(self.who,"in parse_details(), new start : ", start)

        try:
            full_title = self.parse_title_series(soup)
        except:
            self.log.exception('Erreur en cherchant le titre dans : %r' % self.url)
            bbl_title = None
        bbl_title=full_title[0]
        bbl_series=full_title[1]

        if self.debugt:
            self.log.info(self.who,"Temps après parse_title_series() ... : ", time.time() - start)

        try:
            authors = self.parse_authors(root)
        except:
            self.log.info('Erreur en cherchant l\'auteur dans: %r' % self.url)
            authors = []

        if self.debugt:
            self.log.info(self.who,"Temps après parse_authors() ... : ", time.time() - start)

        if not bbl_title or not authors :
            self.log.error('Impossible de trouver le titre/auteur dans %r' % self.url)
            self.log.error('Titre: %r Auteurs: %r' % (bbl_title, authors))
            # return

        mi = Metadata(bbl_title, authors)
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
            self.log.exception('Erreur en cherchant ISBN, éditeur et date de publication dans : %r' % self.url)

        if self.debugt:
            self.log.info(self.who,"Temps après parse_meta() ... : ", time.time() - start)

        try:
            mi.rating = self.parse_rating(root)
        except:
            self.log.exception('Erreur en cherchant la note dans : %r' % self.url)

        if self.debugt:
            self.log.info(self.who,"Temps après parse_rating() ... : ", time.time() - start)

        try:
            mi.comments = self.parse_comments(root).replace('\r\n', '').replace('\r', '').strip()
            if mi.comments == '' :
                self.log.info('Pas de commentaires pour ce livre')
        except:
            self.log.exception('Erreur en cherchant le résumé : %r' % self.url)

        if self.debugt:
            self.log.info(self.who,"Temps après parse_comments() ... : ", time.time() - start)

#        if JSONConfig('plugins/Babelio').get('cover', False) == True:
        if self.with_cover :
            try:
                self.cover_url = self.parse_cover(root)
            except:
                self.log.exception('Erreur en cherchant la couverture dans : %r' % self.url)

        else :
            self.log.info('Téléchargement de la couverture désactivé')
            self.cover_url = None
        mi.has_cover = bool(self.cover_url)

        if self.debugt:
            self.log.info(self.who,"Temps après parse_cover() ... : ", time.time() - start)

        try:
            tags = self.parse_tags(root)
            if tags:
                mi.tags = tags
        except:
            self.log.exception('Erreur en cherchant les étiquettes dans : %r' % self.url)

        if self.debugt:
            self.log.info(self.who,"Temps après parse_tags() ... : ", time.time() - start)

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
        returns either None or a valid bbl_id; bbl_id is a unique id that, combined with
        fixed partial address string, gives the complete url address of the book.
        '''
        self.log.info(self.who,"in parse_bbl_id\n")

        bbl_id = ""
        if "https://www.babelio.com/livres/" in url:
            bbl_id = url.replace("https://www.babelio.com/livres/","").strip()
        if "/" in bbl_id and bbl_id.split("/")[-1].isnumeric():
            if self.debug:
                self.log.info(self.who,"bbl_id : ", bbl_id)
            return bbl_id
        else:
            return None

        # never accessed
        # return re.search(r'/(\d+)', url).groups(0)[0]

    def parse_title_series(self, soup):
        '''
        get the book title from the url
        this title may be located in the <head> or in the <html> part
        '''
        self.log.info(self.who,"in parse_title_series(self, soup)\n")

        # title_node = root.xpath("//div [@class='livre_header_con']/h1/a")
        # if not title_node:
        #     return None
        # title_text = title_node[0].text_content().strip()

      # seems that the title of babelio is in fact of the form "la serie - editeur, tome 55 : le titre"
      # editeur seems to be preceded by - it can be missing
      # tome <num> seems to be surrounded by , and :
      # so we can extract the title always, and the series if babelio title contains ':'
      # if series exist the we can look for tome...
        if soup.select_one(".livre_header_con"):
            if self.debug:
                title_soup=soup.select_one(".livre_header_con").select_one("a")
                self.log.info(self.who,"title_soup prettyfied :\n", title_soup.prettify())

            tmp_ttl=str(soup.select_one(".livre_header_con").select_one("a").string).strip()

            bbl_series, series_seq ="", ""       # serie_seq = 999 means manual check is required
            if ":" and "tome" in tmp_ttl:
                bbl_title=tmp_ttl.split(":")[-1].strip()
                bbl_series=tmp_ttl.replace("-", ",").split(":")[0].split(",")[0].strip()
                if bbl_series:
                    series_seq = tmp_ttl.split("tome")[-1].split(":")[0].strip()
            else:
                bbl_title=tmp_ttl.strip()

        if self.debug:
            # self.log.info(self.who,"title_text is : ", title_text)
            self.log.info(self.who,"tmp_ttl is    : ", tmp_ttl)
            self.log.info(self.who,"bbl_title is  : ", bbl_title)
            self.log.info(self.who,"bbl_series is     : ", bbl_series)
            self.log.info(self.who,"series_seq is : ", series_seq)

        return (bbl_title, bbl_series)

    def parse_authors(self, root):
        '''
        get authors from the url, may be located in head (indirectly) or in the html part
        '''
        debug=self.dbg_lvl & 2
        debugt=self.dbg_lvl & 8
        self.log.info(self.who,"in parse_authors(self, root)\n")

        node_authors = root.xpath(".//*[@id='page_corps']/div/div[3]/div[2]/div[1]/div[2]/span[1]/a/span")
        if not node_authors:
            return
        authors_html = tostring(node_authors[0], method='text', encoding='unicode').replace('\n', '').strip()
        authors = []
        for a in authors_html.split(','):
            authors.append(a.strip())
        return authors

    def parse_rating(self, root):
        '''
        get rating from the url located in the html part
        '''
        self.log.info(self.who,"in parse_rating(self, root)\n")

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
        '''
        get resume in the html part, may need expantion
        '''
        self.log.info(self.who,"in parse_comments(self, root)\n")

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

            if self.debug:                                     # may be long
                soup = BS(comments, "html5lib")
                self.log.info("get details comments prettyfied :\n", soup.prettify())

            return comments.replace(b'\x92', b'\x27').replace(b'\x19', b'\x27').replace(b'\x9C', b'\x6f\x65').decode('latin-1', errors='replace')
        else :
            comments = ''
            if root.xpath('//div [@id="d_bio"]') :
                comments = tostring(root.xpath('//div [@id="d_bio"]')[0], method='text', encoding=str)
            return comments

    def parse_cover(self, root):
        '''
        get cover address either from head or from html part
        '''
        self.log.info(self.who,"in parse_cover(self, root)\n")

        if self.debugt:
            start = time.time()
            self.log.info(self.who,"Temps après parse_cover 0 : ", time.time() - start)

        imgcol_node = root.xpath(".//*[@id='page_corps']/div/div[3]/div[2]/div[1]/div[1]/img")
        if imgcol_node:
            url = imgcol_node[0].get('src')
            img_url = BASE_URL + url
            if self.debugt:
                self.log.info(self.who,"Temps après parse_cover 1 : ", time.time() - start)
            if url.startswith('http'):
                img_url = url
                if self.debugt:
                    self.log.info(self.who,"Temps après parse_cover 2 : ", time.time() - start)
            self.log.info('img_url :', img_url)
          # the following takes forever (amazon site?), let's decide url is correct.
          # anyway when fetching cover this will be accessed before timeout (or not)
            # try :
            #     info = self.browser.open_novisit(img_url, timeout=self.timeout).info()
            #     self.log.info(self.who,"Temps après parse_cover 3 : ", time.time() - start)
            # except :
            #     self.log.warning('Lien pour l\'image invalide : %s' % img_url)
            #     return None
            # #if int(info.getheader('Content-Length')) > 1000:
            # if int(info.get('Content-Length')) > 1000:
            #     self.log.info(self.who,"Temps après parse_cover 4 : ", time.time() - start)
            return img_url
            # else:
            #     self.log.warning('Lien pour l\'image invalide : %s' % img_url)

    def parse_meta(self, root):
        '''
        get publisher, isbn ref, publication date from html part
        '''
        self.log.info(self.who,"in parse_meta(self, root)\n")

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
        '''
        get tags from html part
        '''
        self.log.info(self.who,"in parse_tags(self, root)\n")

        tags_node = root.xpath('//p[@class="tags"]/a[@rel="tag"]')
        if tags_node:
            tags_list = list()
            for tag in tags_node:
                texttag = tag.text.replace('\ufffd', "'")
                tags_list.append(texttag)
            if len(tags_list) > 0:
                return tags_list

    def _convert_date_text(self, date_text):
        '''
        utility to convert date from type string to type datetime
        '''
        self.log.info(self.who,"in _convert_date_text(self, date_text)\n")

        if self.debug:
            self.log.info(self.who,"date_text : ", date_text)

        year = int(date_text[-4:])
        month = 1
        day = 1
        if len(date_text) > 4:
            text_parts = date_text[:len(date_text) - 5].partition(' ')
            month_name = text_parts[0]
            month_dict = {"janvier":1, "février":2, "mars":3, "avril":4, "mai":5, "juin":6,
                "juillet":7, "août":8, "Septembre":9, "octobre":10, "novembre":11, "décembre":12}
            month = month_dict.get(month_name, 2)
            if len(text_parts[2]) > 0:
                day = int(re.match('([0-9]+)', text_parts[2]).groups(0)[0])
        from calibre.utils.date import utc_tz
        return datetime.datetime(year, month, day, tzinfo=utc_tz)
