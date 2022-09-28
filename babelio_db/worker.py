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

    #    cover_url = self.isbn = None
        self.bbl_id = None
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

      # find the babelio id
        try:
            # self.bbl_id = self.parse_bbl_id(self.url)
            self.bbl_id = self.parse_bbl_id(self.url)
        except:
            # self.log.exception("Erreur en cherchant l'id babelio dans : %r" % self.url)
            self.log.exception("Erreur en cherchant l'id babelio dans : %r" % self.url)
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

        # if self.debug: self.log.info(self.who,"get details soup prettyfied :\n", soup.prettify())   # may be very long

            # effect of raw being decoded to latin_1 inside calibre...
            # rawbs=BS(raw, "html5lib")   (raw = raw.decode('latin-1', errors='replace') )
            # self.log.info(self.who,"get details rawbs prettyfied :\n", rawbs.prettify())
            # resultat (court extrait...)
            # Poussé par lamour dune jolie femme, il simprovisera un moment professeur dans une école
            # self.log.info(self.who,"get details soup prettyfied :\n", soup.prettify())
            # resultat (court extrait...)
            # Poussé par l’amour d’une jolie femme, il s’improvisera un moment professeur dans une école

        try:
            root = fromstring(clean_ascii_chars(raw))
        except:
            msg = 'Impossible de parcourir la page : %r' % self.url
            self.log.exception(msg)
            return

        if self.debugt:
            self.log.info(self.who,"Temps après fromstring() ... : ", time.time() - start)

        self.parse_details(root, soup)

    def parse_details(self, root, soup):
        '''
        gathers all details needed to complete the calibre metadata, handels
        errors and sets mi
        '''
        self.log.info(self.who,"in parse_details(self, root, soup)\n")
        if self.debug:
            self.log.info(self.who,"type(root) : ", type(root))
            self.log.info(self.who,"type(soup) : ", type(soup))
        if self.debugt:
            start = time.time()
            self.log.info(self.who,"in parse_details(), new start : ", start)

      # find title, serie and serie_seq.. OK
        try:
            bbl_title, bbl_series, bbl_series_seq = self.parse_title_series(soup)
        except:
            self.log.exception('Erreur en cherchant le titre dans : %r' % self.url)
            bbl_title = None

        if self.debugt:
            self.log.info(self.who,"Temps après parse_title_series() ... : ", time.time() - start)

      # find authors.. OK
        try:
            bbl_authors = self.parse_authors(soup)
        except:
            self.log.info('Erreur en cherchant l\'auteur dans: %r' % self.url)
            bbl_authors = []

        if self.debugt:
            self.log.info(self.who,"Temps après parse_authors() ... : ", time.time() - start)

        if not bbl_title or not bbl_authors :
            self.log.error('Impossible de trouver le titre/auteur dans %r' % self.url)
            self.log.error('Titre: %r Auteurs: %r' % (bbl_title, bbl_authors))
            # return


        mi = Metadata(bbl_title, bbl_authors)


      # find isbn (EAN), publisher and publication date.. ok
        try:
            bbl_isbn, bbl_publisher, bbl_pubdate = self.parse_meta(root, soup)

        except:
            self.log.exception('Erreur en cherchant ISBN, éditeur et date de publication dans : %r' % self.url)

        if self.debugt:
            self.log.info(self.who,"Temps après parse_meta() ... : ", time.time() - start)
            bbl_isbn, bbl_pubdate, bbl_publisher = None, None, None

      # find the rating.. OK
        try:
            bbl_rating = self.parse_rating(soup)
        except:
            self.log.exception('Erreur en cherchant la note dans : %r' % self.url)
            bbl_rating = None

        if self.debugt:
            self.log.info(self.who,"Temps après parse_rating() ... : ", time.time() - start)

      # get the tags.. OK
        try:
            bbl_tags = self.parse_tags(soup)

        except:
            self.log.exception('Erreur en cherchant les étiquettes dans : %r' % self.url)
            bbl_tags = None

        if self.debugt:
            self.log.info(self.who,"Temps après parse_tags() ... : ", time.time() - start)

      # get the cover address, set the cache address.. ok
        if self.with_cover:
            try:
                bbl_cover_url = self.parse_cover(soup)
            except:
                self.log.exception('Erreur en cherchant la couverture dans : %r' % self.url)
                bbl_cover_url = None
            if bbl_cover_url:       # cache cover info ONLY if cover valid and desired
                if self.bbl_id:
                    if bbl_isbn:
                        self.plugin.cache_isbn_to_identifier(bbl_isbn, self.bbl_id)
                    if bbl_cover_url:
                        self.plugin.cache_identifier_to_cover_url(self.bbl_id, bbl_cover_url)
        else :
          self.log.info('Téléchargement de la couverture désactivé')
          bbl_cover_url = None

        if self.debugt:
            self.log.info(self.who,"Temps après parse_cover() ... : ", time.time() - start)

      # find the comments..  OK
      # and format them in a fixed structure for the catalog... bof
      # I just extract the text and it is ok but formating lost...
        comments = None
        try:
            # mi.comments = self.orig_parse_comments(root).replace('\r\n', '').replace('\r', '').strip()
            # if mi.comments == '' :
            #     self.log.info('Pas de commentaires pour ce livre')

            comments = self.parse_comments(soup)
            if self.debug: self.log.info('comments :\n', comments)
            mi.comments=comments
            if not comments:
                self.log.info('Pas de résumé pour ce livre')
        except:
            self.log.exception('Erreur en cherchant le résumé : %r' % self.url)

        if self.debugt:
            self.log.info(self.who,"Temps après parse_comments() ... : ", time.time() - start)

      # set the matadata fields
        # mi = Metadata(bbl_title, bbl_authors) laissé au dessus pour eviter errors...
        mi.series = bbl_series
        if bbl_series:
            mi.series_index = bbl_series_seq
        mi.rating = bbl_rating
        if bbl_isbn:
            mi.isbn = bbl_isbn
        if bbl_publisher:
            mi.publisher = bbl_publisher
        if bbl_pubdate :
            mi.pubdate = bbl_pubdate
        mi.has_cover = bool(bbl_cover_url)
        mi.set_identifier('babelio', self.bbl_id)
        mi.language = 'fr'
        mi.tags = bbl_tags
        mi.isbn = check_isbn(mi.isbn)
        # mi.comments = bbl_comments

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

      # seems that the title of babelio is in fact of the form "la serie - editeur, tome 55 : le titre"
      #
      # editeur seems to be preceded by - it can be missing... AND "-" may be part of serie: "grande-série"
      # tome <num> seems to be surrounded by , or - and :
      # title may include a : hopefully rare enough and NOT associated with a serie (should I look for " : " instead, or ???)
      # so we can extract the title always, and the series if babelio title contains both ':' and tome
      # series_seq is found just after tome and is numeric...

      # if soup.select_one(".livre_header_con") fails, an exception will be raised
        if self.debug:
            title_soup=soup.select_one(".livre_header_con").select_one("a")
            self.log.info(self.who,"title_soup prettyfied :\n", title_soup.prettify())
        tmp_ttl=soup.select_one(".livre_header_con").select_one("a").text.strip()
        bbl_series, bbl_series_seq ="", ""
        if ":" and "tome" in tmp_ttl:
            bbl_title=tmp_ttl.split(":")[-1].strip()
            bbl_series=tmp_ttl.replace(" -", ",").split(":")[0].split(",")[0].strip()
            if bbl_series:
                bbl_series_seq = tmp_ttl.split("tome")[-1].split(":")[0].strip()
                if bbl_series_seq.isnumeric:
                    bbl_series_seq = float(bbl_series_seq)
                else:
                    bbl_series_seq = 0.0
        else:
            bbl_title=tmp_ttl.strip()


        if self.debug:
            # self.log.info(self.who,"title_text is : ", title_text)
            self.log.info(self.who,"tmp_ttl         : ", tmp_ttl)
            self.log.info(self.who,"bbl_title       : ", bbl_title)
            self.log.info(self.who,"bbl_series      : ", bbl_series)
            self.log.info(self.who,"bbl_series_seq  : ", bbl_series_seq)

        return (bbl_title, bbl_series, bbl_series_seq)

    def parse_authors(self, soup):
        '''
        get authors from the url, may be located in head (indirectly) or in the html part
        '''
        self.log.info(self.who,"in parse_authors(self, soup)\n")

        if self.debug:
            self.log.info(self.who,"type(soup) : ", type(soup))

      # if soup.select_one(".livre_con") fails, an exception will be raised
        authors_soup=soup.select_one(".livre_con").select('span[itemprop="author"]')
        bbl_autors=[]
        for i in range(len(authors_soup)):
          # if self.debug: self.log.info(self.who,"authors_soup prettyfied #",i," :\n", authors_soup[i].prettify())
            tmp_thrs = authors_soup[i].select_one('span[itemprop="name"]').text.split()
            thrs=" ".join(tmp_thrs)
          # if self.debug: self.log.info(self.who,"tmp_thrs : ",tmp_thrs, thrs)
            bbl_autors.append(thrs)
        if self.debug:
            self.log.info(self.who,"bbl_autors : ", bbl_autors)

        bbl_autors = fixauthors(bbl_autors)

        if self.debug:
            self.log.info(self.who,"return bbl_autors", bbl_autors)

        return bbl_autors

    def parse_rating(self, soup):
        '''
        get rating from the url located in the html part
        '''
        self.log.info(self.who,"in parse_rating(self, soup)\n")

      # if soup.select_one('span[itemprop="aggregateRating"]') fails, an exception will be raised
        rating_soup=soup.select_one('span[itemprop="aggregateRating"]').select_one('span[itemprop="ratingValue"]')
      # if self.debug: self.log.info(self.who,"rating_soup prettyfied :\n",rating_soup.prettify())
        bbl_rating = float(rating_soup.text.strip())

        if self.debug:
            self.log.info(self.who,'parse_rating() returns bbl_rating : ', bbl_rating)
        return bbl_rating

    def parse_comments(self,soup):
        '''
        get resume from soup, may need access to the page again.
        Returns it with at title, html formatted.
        '''
        self.log.info(self.who,"in parse_comments(self, root)\n")

        comments_soup = soup.select_one('.livre_resume')
      # if self.debug: self.log.info(self.who,"comments prettyfied:\n", comments_soup.prettify())
        if comments_soup.select_one('a[onclick]'):
            if self.debug:
                self.log.info(self.who,"onclick : ",comments_soup.select_one('a[onclick]')['onclick'])
            tmp_nclck = comments_soup.select_one('a[onclick]')['onclick'].split("(")[-1].split(")")[0].split(",")
            rkt = {"type":tmp_nclck[1],"id_obj":tmp_nclck[2]}
            url = "https://www.babelio.com/aj_voir_plus_a.php"
            if self.debug:
                self.log.info(self.who,"calling ret_soup(log, dbg_lvl, br, url, rkt=rkt, who=self.who")
                self.log.info(self.who,"url : ",url)
                self.log.info(self.who,"rkt : ",rkt)
            comments_soup = ret_soup(self.log, self.dbg_lvl, self.br, url, rkt=rkt, who=self.who)[0]

        tmp_cmmnts = comments_soup.text
        if self.debug: self.log.info(self.who,"tmp_cmmnts :\n", tmp_cmmnts)

        return tmp_cmmnts

    # def orig_parse_comments(self, root):
    #     '''
    #     get resume from root, may need access to the page again
    #     '''
    #     self.log.info(self.who,"in orig_parse_cover(self, root)\n")

    #     description_node = root.xpath('//div [@id="d_bio"]/span/a')
    #     if description_node:
    #         java = description_node[0].get('onclick')
    #         hash_url = re.search(r',([0-9]+?),([0-9]*)\)', java)
    #         comment_url = BASE_URL + '/aj_voir_plus_a.php'
    #         data = urllib.parse.urlencode({'type':hash_url.group(1), 'id_obj':hash_url.group(2) })
    #         req = mechanize.Request(comment_url, data)
    #         req.add_header('X-Requested-With', 'XMLHttpRequest')
    #         req.add_header('Referer', self.url)
    #         req.add_header('Host', 'www.babelio.com')
    #         req.add_header('Connection', 'Keep-Alive')
    #         req.add_header('Content-Type', 'application/x-www-form-urlencoded; charset=UTF-8')
    #         req.add_header('Accept', '*/*')
    #         handle = self.browser.open_novisit(req)
    #         comments = handle.read()

    #         if self.debug:                                     # may be long
    #             soup = BS(comments, "html5lib")
    #             self.log.info("get details comments prettyfied :\n", soup.prettify())

    #         return comments.replace(b'\x92', b'\x27').replace(b'\x19', b'\x27').replace(b'\x9C', b'\x6f\x65').decode('latin-1', errors='replace')
    #     else :
    #         comments = ''
    #         if root.xpath('//div [@id="d_bio"]') :
    #             comments = tostring(root.xpath('//div [@id="d_bio"]')[0], method='text', encoding=str)
    #         return comments

    def parse_cover(self, soup):
        '''
        get cover address either from head or from html part
        '''
        self.log.info(self.who,"in parse_cover(self, soup)\n")

        # if self.debugt:
        #     start = time.time()
        #     self.log.info(self.who,"Temps après parse_cover 0 : ", time.time() - start)

      # if soup.select_one('link[rel="image_src"]') fails, an exception will be raised
        cover_soup = soup.select_one('link[rel="image_src"]')
        # if self.debug: self.log.info(self.who,"cover_soup prettyfied :\n", cover_soup.prettify())
        bbl_cover = cover_soup['href']

        if self.debug:
            self.log.info(self.who,'parse_cover() returns bbl_cover : ', bbl_cover)

        return bbl_cover

        # imgcol_node = root.xpath(".//*[@id='page_corps']/div/div[3]/div[2]/div[1]/div[1]/img")
        # if imgcol_node:
        #     url = imgcol_node[0].get('src')
        #     img_url = BASE_URL + url
        #     if self.debugt:
        #         self.log.info(self.who,"Temps après parse_cover 1 : ", time.time() - start)
        #     if url.startswith('http'):
        #         img_url = url
        #         if self.debugt:
        #             self.log.info(self.who,"Temps après parse_cover 2 : ", time.time() - start)
        #     self.log.info('img_url :', img_url)
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
            # return img_url
            # else:
            #     self.log.warning('Lien pour l\'image invalide : %s' % img_url)

    def parse_meta(self, root, soup):
        '''
        get publisher, isbn ref, publication date from html part
        '''
        self.log.info(self.who,"in parse_meta(self, root)\n")

      # if soup.select_one(".livre_refs.grey_light") fails it will produce an exception
      # note: when a class contains white characters use a dot instead
      # (blank means 2 subsequent classes for css selector)
        meta_soup = soup.select_one(".livre_refs.grey_light")
        # self.log.info(self.who,"meta_soup prettyfied :\n",meta_soup.prettify())

        bbl_publisher = None
        if meta_soup.select_one('a[href^="/editeur"]'):
            bbl_publisher = meta_soup.select_one('a[href^="/editeur"]').text.strip()
            if self.debug:
                self.log.info(self.who,"bbl_publisher processed : ", bbl_publisher)

        bbl_isbn, bbl_pubdate = None, None
        for mta in (meta_soup.stripped_strings):
            if "EAN" in mta:
                tmp_sbn = mta.split()
                bbl_isbn = check_isbn(tmp_sbn[-1])
                if self.debug:
                    self.log.info(self.who,"bbl_isbn processed : ", bbl_isbn)
            elif "/" in mta:
                tmp_dt = mta.strip().replace("(","").replace(")","")
                tmp_pbdt=tmp_dt.split("/")
                # if self.debug: self.log.info(self.who,"tmp_pbdt : ", tmp_pbdt)
                for i in range(len(tmp_pbdt)):
                    if tmp_pbdt[i].isnumeric:
                        if i==0 and int(tmp_pbdt[i]) <= 31: continue
                        elif i==1 and int(tmp_pbdt[i]) <= 12 : continue
                        elif i==2 and int(tmp_pbdt[i]) > 1700:    # reject year -1, assumes no book in with date < 1700
                            bbl_pubdate = datetime.datetime.strptime(tmp_dt,"%j/%m/%Y")
                            if self.debug:
                                self.log.info(self.who,"bbl_pubdate processed : ", bbl_pubdate)

        if self.debug:
            self.log.info(self.who,'parse_meta() returns bbl_isbn, bbl_publisher, bbl_pubdate : '
                            , bbl_isbn, bbl_publisher, bbl_pubdate)

        return bbl_isbn, bbl_publisher, bbl_pubdate

        # meta_node = root.xpath(".//*[@id='page_corps']/div/div[3]/div[2]/div[1]/div[2]/div[1]")
        # if meta_node:
        #     publisher_re = isbn_re = pubdate_re = publication = None
        #     meta_text = tostring(meta_node[0], method='text', encoding=str).strip()
        #     if re.search(r'(?<=teur : )([^\n(]*)', meta_text):
        #         publisher_re = re.search(r'(?<=teur : )([^\n(]*)', meta_text).group(0)
        #     if re.search(r'(?<=[BN|bn] : )([^\n]*)', meta_text) :
        #         isbn_re = re.search(r'(?<=[BN|bn] : )([^\n(]*)', meta_text).group(0)
        #     if re.search(r'\(([0-9]{4})\)', meta_text):
        #         pubdate_re = re.search(r'\(([0-9]{4})\)', meta_text).group(1)
        #         publication = self._convert_date_text(pubdate_re)
        #     # meta_re = re.search(r'.*?\s?:\s?(\w*)\s*\n?.*?\s?:\s?([^\n]*)\n?\(([0-9]{4})\)', meta_text)
        #     # self.log.info(isbn_re, '  ', publisher_re, '  ', pubdate_re)
        #     return isbn_re, publisher_re, publication

    def parse_tags(self, soup):
        '''
        get tags from html part
        '''
        self.log.info(self.who,"in parse_tags(self, soup)\n")

      # if soup.select_one('.tags') fails it will produce an exception
        tag_soup=soup.select_one('.tags')
        # if self.debug: self.log.info(self.who,"tag_soup prettyfied :\n",tag_soup.prettify())
        tag_soup = soup.select_one('.tags').select('a')
        bbl_tags=[]
        for i in range(len(tag_soup)):
            # if self.debug: self.log.info(self.who,"type(tag_soup[i])", type(tag_soup[i]))
            tmp_tg = tag_soup[i].text.strip()
            # if self.debug: self.log.info(self.who,tmp_tg)
            bbl_tags.append(tmp_tg)

        bbl_tags = list(map(fixcase, bbl_tags))

        if self.debug:
                self.log.info(self.who,"parse_tags() return bbl_tags", bbl_tags)

        # tags_node = root.xpath('//p[@class="tags"]/a[@rel="tag"]')
        # if tags_node:
        #     tags_list = list()
        #     for tag in tags_node:
        #         texttag = tag.text.replace('\ufffd', "'")
        #         tags_list.append(texttag)
        #     if len(tags_list) > 0:
        #         return tags_list

    # def _convert_date_text(self, date_text):
    #     '''
    #     utility to convert date from type string to type datetime
    #     '''
    #     self.log.info(self.who,"in _convert_date_text(self, date_text)\n")

    #     if self.debug:
    #         self.log.info(self.who,"date_text : ", date_text)

    #     year = int(date_text[-4:])
    #     month = 1
    #     day = 1
    #     if len(date_text) > 4:
    #         text_parts = date_text[:len(date_text) - 5].partition(' ')
    #         month_name = text_parts[0]
    #         month_dict = {"janvier":1, "février":2, "mars":3, "avril":4, "mai":5, "juin":6,
    #             "juillet":7, "août":8, "Septembre":9, "octobre":10, "novembre":11, "décembre":12}
    #         month = month_dict.get(month_name, 2)
    #         if len(text_parts[2]) > 0:
    #             day = int(re.match('([0-9]+)', text_parts[2]).groups(0)[0])
    #     from calibre.utils.date import utc_tz
    #     return datetime.datetime(year, month, day, tzinfo=utc_tz)
