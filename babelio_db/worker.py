#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai

__license__ = 'GPL v3'
__copyright__ = '2021, Louis Richard Pirlet using VdF work as a base'
__docformat__ = 'restructuredtext en'

import datetime
import time
from bs4 import BeautifulSoup as BS
from threading import Thread

from calibre.ebooks.metadata.book.base import Metadata
from calibre.ebooks.metadata import check_isbn
from calibre.ebooks.metadata.sources.base import fixcase, fixauthors
from calibre_plugins.babelio_db import ret_soup, Babelio

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
        self.br = browser.clone_browser()
        self.dbg_lvl = dbg_lvl

        self.with_cover = self.plugin.with_cover
        self.with_pretty_comments = self.plugin.with_pretty_comments
        self.bbl_id = None
        self.who = "[worker "+str(relevance)+"]"
        self.debug=self.dbg_lvl & 2
        self.debugt=self.dbg_lvl & 8

        if self.debug:
            self.log.info(self.who,"self.url                  : ", self.url)
            self.log.info(self.who,"self.relevance            : ", self.relevance)
            self.log.info(self.who,"self.plugin               : ", self.plugin)
            self.log.info(self.who,"self.dbg_lvl              : ", self.dbg_lvl)
            self.log.info(self.who,"self.timeout              : ", self.timeout)
            self.log.info(self.who,"self.with_cover           : ", self.with_cover)
            self.log.info(self.who,"self.with_pretty_comments : ", self.with_pretty_comments)

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
            self.log.info(self.who,"calling ret_soup(log, dbg_lvl, br, url, rkt=None, who='')")
            self.log.info(self.who,"self.url : ", self.url, "\n")

      # get the babelio page content
        rsp = ret_soup(self.log, self.dbg_lvl, self.br, self.url, who=self.who)
        soup = rsp[0]

        if self.debugt:
            self.log.info(self.who,"Temps après ret_soup()... : ", time.time() - start)

        # if self.debug: self.log.info(self.who,"get details soup prettyfied :\n", soup.prettify())   # may be very long

      # find the babelio id
        try:
            self.bbl_id = self.parse_bbl_id(self.url)
        except:
            self.log.exception("Erreur en cherchant l'id babelio dans : %r" % self.url)
            self.bbl_id = None

        if self.debugt:
            self.log.info(self.who,"Temps après parse_bbl_id() ... : ", time.time() - start)

        self.parse_details(soup)

    def parse_details(self, soup):
        '''
        gathers all details needed to complete the calibre metadata, handels
        errors and sets mi
        '''
        self.log.info(self.who,"in parse_details(self, soup)\n")
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

        if not bbl_title or not bbl_authors :
            self.log.error('Impossible de trouver le titre/auteur dans %r' % self.url)
            self.log.error('Titre: %r Auteurs: %r' % (bbl_title, bbl_authors))
            # return

        if self.debugt:
            self.log.info(self.who,"Temps après parse_authors() ... : ", time.time() - start)

      # find isbn (EAN), publisher and publication date.. ok
        bbl_isbn, bbl_pubdate, bbl_publisher = None, None, None
        try:
            bbl_isbn, bbl_publisher, bbl_pubdate = self.parse_meta(soup)

        except:
            self.log.exception('Erreur en cherchant ISBN, éditeur et date de publication dans : %r' % self.url)

        if self.debugt:
            self.log.info(self.who,"Temps après parse_meta() ... : ", time.time() - start)

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
      # and format them in a fixed structure for the catalog... OK
      # If the text only, it is ok the but formating is lost... a bit sad
      # when author wants a new line in the text: conversation between fictional characters
      # so I will "impose" html comments but leave choice on pretty_comments.. OK
        comments = None
        try:
          # si on retourne du HTML et si (__init__.py) has_html_comments = True
            comments = self.parse_comments(soup)
        except:
            self.log.exception('Erreur en cherchant le résumé : %r' % self.url)

      # keep actual behavior
        if not self.with_pretty_comments:
            self.log.info(self.who,"with_pretty_comments : ", self.with_pretty_comments)
            bbl_comments = comments          # cree la référence (pour retrouver l'url babelio a partir du catalogue)
        else:
            bbl_reference = BS('<div><p>Référence: <a href="' + self.url + '">' + self.url + '</a></p></div>',"lxml")
          # on commence par la référence qui sera toujours presente dans le commentaire si with_pretty_comments est True
            bbl_comments = bbl_reference
          # cree un titre si du commentaire existe
            if comments:
                bbl_titre = BS('<div><hr><p style="font-weight: bold; font-size: 18px"> Résumé </p><hr></div>',"lxml")
              # on rajoute le titre et le commentaire
                bbl_comments.append(bbl_titre)      # ensuite le titre
                bbl_comments.append(comments)       # on ajoute les commentatires

        if bbl_comments:
#            if self.debug: self.log.info(self.who,'bbl_comments prettyfied:\n', bbl_comments.prettify())     # visualise la construction html, may be long...
            bbl_comments = bbl_comments.encode('ascii','xmlcharrefreplace')     # et on serialize le tout
        else:
            self.log.info('Pas de résumé pour ce livre')

        if self.debugt:
            self.log.info(self.who,"Temps après parse_comments() ... : ", time.time() - start)

      # set the matadata fields
        mi = Metadata(bbl_title, bbl_authors)
        mi.series = bbl_series
        if bbl_series:
            mi.series_index = bbl_series_seq
        mi.rating = bbl_rating
        if bbl_isbn:
            mi.isbn = check_isbn(bbl_isbn)
        if bbl_publisher:
            mi.publisher = bbl_publisher
        if bbl_pubdate :
            mi.pubdate = bbl_pubdate
        mi.has_cover = bool(bbl_cover_url)
        mi.set_identifier(Babelio.ID_NAME, self.bbl_id)
        mi.language = 'fr'
        mi.tags = bbl_tags
        mi.comments=bbl_comments

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

    def parse_title_series(self, soup):
        '''
        get the book title from the url
        this title may be located in the <head> or in the <html> part
        '''
        self.log.info(self.who,"in parse_title_series(self, soup)\n")

      # if soup.select_one(".livre_header_con") fails, an exception will be raised
        if self.debug:
            title_soup=soup.select_one(".livre_header_con").select_one("a")
#            self.log.info(self.who,"title_soup prettyfied :\n", title_soup.prettify()) # may be long
        tmp_ttl=soup.select_one(".livre_header_con").select_one("a").text.strip()
        bbl_series, bbl_series_seq ="", ""
        tmp_ttl=tmp_ttl.replace("Tome","tome")
        if ":" and "tome" in tmp_ttl:
            bbl_title=tmp_ttl.split(":")[-1].strip()
            bbl_series=tmp_ttl.replace(" -", ",").split(":")[0].split(",")[0].strip()
            if bbl_series:
                bbl_series_seq = tmp_ttl.replace(bbl_title,"").replace(":","").split("tome")[-1].strip()
                if bbl_series_seq.isnumeric():
                    bbl_series_seq = float(bbl_series_seq)
                else:
                    bbl_series_seq = 0.0
        else:
            bbl_title=tmp_ttl.strip()

        if self.debug:
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

    def parse_comments(self, soup):
        '''
        get resume from soup, may need access to the page again.
        Returns it with at title, html formatted.
        '''
        self.log.info(self.who,"in parse_comments(self, soup)\n")

        comments_soup = soup.select_one('.livre_resume')
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
            comments_soup = ret_soup(self.log, self.dbg_lvl, self.br, url, rkt=rkt, who=self.who, wtf=1)[0]

      # if self.debug: self.log.info(self.who,"comments prettyfied:\n", comments_soup.prettify())
        return comments_soup

    def parse_cover(self, soup):
        '''
        get cover address either from head or from html part
        '''
        self.log.info(self.who,"in parse_cover(self, soup)\n")


      # if soup.select_one('link[rel="image_src"]') fails, an exception will be raised
        cover_soup = soup.select_one('link[rel="image_src"]')
        # if self.debug: self.log.info(self.who,"cover_soup prettyfied :\n", cover_soup.prettify())
        bbl_cover = cover_soup['href']

        if self.debug:
            self.log.info(self.who,'parse_cover() returns bbl_cover : ', bbl_cover)

        return bbl_cover

    def parse_meta(self, soup):
        '''
        get publisher, isbn ref, publication date from html part
        '''
        self.log.info(self.who,"in parse_meta(self, soup)\n")

      # if soup.select_one(".livre_refs.grey_light") fails it will produce an exception
      # note: when a class name contains white characters use a dot instead of the space
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
                    if tmp_pbdt[i].isnumeric():
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

        return bbl_tags
