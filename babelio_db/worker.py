#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai

__license__ = 'GPL v3'
__copyright__ = '2021, Louis Richard Pirlet using VdF work as a base'
__docformat__ = 'restructuredtext en'

import datetime
import time
from bs4 import BeautifulSoup as BS
from threading import Thread

from psutil import cpu_count                    # goal is to set a minimum access time of 1 sec * number of thread available: this to avoid a DoS detection
TIME_INTERVAL = 2

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
        self.with_detailed_rating = self.plugin.with_detailed_rating
        self.bbl_id = None
        self.who = "[worker "+str(relevance)+"]"
        self.debug=self.dbg_lvl & 2
        self.debugt=self.dbg_lvl & 8

        if self.debug:
            self.log.info(self.who,"entry time                : ", time.asctime())
            self.log.info(self.who,"self.url                  : ", self.url)
            self.log.info(self.who,"self.relevance            : ", self.relevance)
            self.log.info(self.who,"self.plugin               : ", self.plugin)
            self.log.info(self.who,"self.dbg_lvl              : ", self.dbg_lvl)
            self.log.info(self.who,"self.timeout              : ", self.timeout)
            self.log.info(self.who,"self.with_cover           : ", self.with_cover)
            self.log.info(self.who,"self.with_pretty_comments : ", self.with_pretty_comments)
            self.log.info(self.who,"self.with_detailed_rating : ", self.with_detailed_rating)

    def run(self):
        '''
        this control the rest of the worker process
        '''
        self.log.info("\n"+self.who,"in run(self)")

        time.sleep(self.relevance%cpu_count()* TIME_INTERVAL/cpu_count())

        try:
            self.get_details()
        except:
            self.log.exception('get_details failed for url: %r' % self.url)

    def get_details(self):
        '''
        sets details this code uploads url then calls parse_details
        '''
        self.log.info("\n"+self.who,"in get_details(self)")
        if self.debugt:
            start = time.time()
            self.log.info(self.who,"in get details(), start time : ", start)
        if self.debug:
            self.log.info(self.who,"calling ret_soup(log, dbg_lvl, br, url, rkt=None, who='')")
            self.log.info(self.who,"self.url : ", self.url, "")

      # get the babelio page content
        rsp = ret_soup(self.log, self.dbg_lvl, self.br, self.url, who=self.who)
        soup = rsp[0]

        if self.debugt:
            self.log.info(self.who,"Temps après ret_soup()... : ", time.time() - start)

        # if self.debug: self.log.info(self.who,"get details soup prettyfied :\n", soup.prettify())   # hide_it  #may be very long

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
        self.log.info("\n"+self.who,"in parse_details(self, soup)")
        if self.debugt:
            start = time.time()
            self.log.info(self.who,"in parse_details(), new start : ", start)

      # find authors.. OK
        try:
            bbl_authors = self.parse_authors(soup)
        except:
            self.log.info('Erreur en cherchant l\'auteur dans: %r' % self.url)
            bbl_authors = []

        if self.debugt:
            self.log.info(self.who,"Temps après parse_authors() ... : ", time.time() - start)

      # find title, serie and serie_seq.. OK
        try:
            bbl_title, bbl_series, bbl_series_seq, bbl_series_url = self.parse_title_series(soup, bbl_authors)
        except:
            self.log.exception('Erreur en cherchant le titre dans : %r' % self.url)
            bbl_title = None

        if self.debugt:
            self.log.info(self.who,"Temps après parse_title_series() ... : ", time.time() - start)

        if not bbl_title or not bbl_authors :
            self.log.error('Impossible de trouver le titre/auteur dans %r' % self.url)
            self.log.error('Titre: %r Auteurs: %r' % (bbl_title, bbl_authors))
            # return

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
            bbl_rating, bbl_rating_cnt = self.parse_rating(soup)
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
      # when author wants a new line in the text: conversion between fictional characters
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
          # si part d'une série, crèe et ajoute la référence à la série.
            if bbl_series_url:
                bbl_serie_ref = BS('<div><p>Réf. de la série: <a href="' + bbl_series_url + '">' + bbl_series_url + '</a></p></div>',"lxml")
                bbl_comments.append(bbl_serie_ref)  # si part d'une série, ajoute la référence à la série.
          # cree la note détaillée
            if bbl_rating and bbl_rating_cnt and self.with_detailed_rating:
                bbl_titre = BS('<div><hr><p style="font-weight: bold; font-size: 18px"> Popularité </p><hr></div>',"lxml")
                bbl_ext_rating = BS('<div><p>Le nombre de cotations est <strong>' + str(bbl_rating_cnt) + '</strong>, avec une note moyenne de <strong>' + str(bbl_rating) + '</strong> sur 5</p></div>',"lxml")
                bbl_comments.append(bbl_titre)      # ensuite le titre
                bbl_comments.append(bbl_ext_rating)
          # cree un titre si du commentaire existe
            if comments:
                bbl_titre = BS('<div><hr><p style="font-weight: bold; font-size: 18px"> Résumé </p><hr></div>',"lxml")
              # on ajoute le titre et le commentaire
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
        self.log.info("\n"+self.who,"in parse_bbl_id")

        bbl_id = ""
        if "https://www.babelio.com/livres/" in url:
            bbl_id = url.replace("https://www.babelio.com/livres/","").strip()
        if "/" in bbl_id and bbl_id.split("/")[-1].isnumeric():
            if self.debug:
                self.log.info(self.who,"bbl_id : ", bbl_id)
            return bbl_id
        else:
            return None

    def parse_title_series(self, soup, bbl_authors):
        '''
        get the book title from the url
        this title may be located in the <head> or in the <html> part
        '''
        self.log.info("\n"+self.who,"in parse_title_series(self, soup, bbl_authors)")

      # if soup.select_one(".livre_header_con") fails, an exception will be raised
        bbl_series, bbl_series_seq, bbl_series_url = "", "", ""

      # get the title

        bbl_title = soup.select_one("head>title").string.replace(" - Babelio","").strip()   # returns  titre - auteur - Babelio
        self.log.info(self.who,'bbl_title : ', bbl_title)                                   # exemple: <title>Hope one, tome 2 -  Fane - Babelio</title>
        for name in bbl_authors:
            self.log.info(self.who,'name : ', name)
            if name in bbl_title:
                bbl_title = bbl_title.split(name)[0].strip(" -")                            # écarte separation, auteur et le reste...

      # get the series
        if soup.select_one('a[href^="/serie/"]'):

          # find true url for the series
            es_url = "https://www.babelio.com" + soup.select_one('a[href^="/serie/"]').get('href')
            if self.debug:
                self.log.info(self.who,'url de la serie :', es_url)

          # get series infos from the series page
            try:
                bbl_series, bbl_series_seq, bbl_series_url = self.parse_extended_serie(es_url, bbl_title)
            except:
                self.log.exception('Erreur en cherchant la serie dans : %r' % es_url)

          # ne garde que l'essence du titre
        bbl_title=bbl_title.replace("Tome","tome")          # remplace toute instance de Tome par tome
        if "tome" and ":" in bbl_title:
            bbl_title = bbl_title.split(":")[-1].strip()

        if self.debug:
            self.log.info(self.who,"bbl_title       : ", bbl_title)

        return (bbl_title, bbl_series, bbl_series_seq, bbl_series_url)

    def parse_extended_serie(self, es_url, bbl_title):
        '''
        a serie url exists then this get the page,
        extract the serie name and the url according to babelio
        '''
        self.log.info("\n"+self.who,"parse_extended_serie(self, es_url, bbl_title : {})".format(bbl_title))

        bbl_series, bbl_series_seq ="", ""

        es_rsp = ret_soup(self.log, self.dbg_lvl, self.br, es_url, who=self.who)
        es_soup = es_rsp[0]
        bbl_series_url = es_rsp[1]
#         self.log.info(self.who,"es_soup prettyfied :\n", es_soup.prettify()) # hide_it # may be long

        bbl_series = (es_soup.select_one("head>title").string).split("érie")[0].rstrip(" -Ss").strip()

        for i in es_soup.select(".cr_droite"):
#             self.log.info(self.who,"es_soup.select('.cr_droite').get_text() :\n", i.get_text()) # may be long
            if bbl_title in i.get_text():
                bbl_series_seq = i.get_text().split('tome :')[-1].strip()
                if bbl_series_seq.isnumeric():
                    bbl_series_seq = float(bbl_series_seq)
                break

        if self.debug:
            self.log.info(self.who,"bbl_series      : ", bbl_series)
            self.log.info(self.who,"bbl_series_seq  : ", bbl_series_seq)
            self.log.info(self.who,"bbl_series_url  : ", bbl_series_url)

        return (bbl_series, bbl_series_seq, bbl_series_url)


    def parse_authors(self, soup):
        '''
        get authors from the url, may be located in head (indirectly) or in the html part
        '''
        self.log.info("\n"+self.who,"in parse_authors(self, soup)")

      # if soup.select_one(".livre_con") fails, an exception will be raised
        sub_soup=soup.select_one(".livre_con")
        # self.log.info(self.who,"sub_soup prettyfied # :\n", sub_soup.prettify()) # hide_it
        authors_soup=sub_soup.select('span[itemprop="author"]')
        bbl_authors=[]
        for i in range(len(authors_soup)):
            # self.log.info(self.who,"authors_soup prettyfied #",i," :\n", authors_soup[i].prettify()) # hide_it
            tmp_thrs = authors_soup[i].select_one('span[itemprop="name"]').text.split()
            thrs=" ".join(tmp_thrs)
            bbl_authors.append(thrs)

        if self.debug:
            self.log.info(self.who,"return bbl_authors", bbl_authors)

        return bbl_authors

    def parse_rating(self, soup):
        '''
        get rating and number of votes from the url located in the html part
        '''
        self.log.info("\n"+self.who,"in parse_rating(self, soup)")

      # if soup.select_one('span[itemprop="aggregateRating"]') fails, an exception will be raised
        rating_soup = soup.select_one('span[itemprop="aggregateRating"]').select_one('span[itemprop="ratingValue"]')
        # if self.debug: self.log.info(self.who,"rating_soup prettyfied :\n",rating_soup.prettify()) # hide_it
        bbl_rating = float(rating_soup.text.strip())
        rating_cnt_soup = soup.select_one('span[itemprop="aggregateRating"]').select_one('span[itemprop="ratingCount"]')
        # if self.debug: self.log.info(self.who,"rating_soup prettyfied :\n",rating_soup.prettify()) # hide_it
        bbl_rating_cnt = int(rating_cnt_soup.text.strip())

        if self.debug:
            self.log.info(self.who,"parse_rating() returns bbl_rating : {}, bbl_rating_cnt : {}".format(bbl_rating, bbl_rating_cnt))
        return bbl_rating, bbl_rating_cnt

    def parse_comments(self, soup):
        '''
        get resume from soup, may need access to the page again.
        Returns it with at title, html formatted.
        '''
        self.log.info("\n"+self.who,"in parse_comments(self, soup)")

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
            comments_soup = ret_soup(self.log, self.dbg_lvl, self.br, url, rkt=rkt, who=self.who)[0]

      # if self.debug: self.log.info(self.who,"comments prettyfied:\n", comments_soup.prettify()) # hide_it
        return comments_soup

    def parse_cover(self, soup):
        '''
        get cover address either from head or from html part
        '''
        self.log.info("\n"+self.who,"in parse_cover(self, soup)")


      # if soup.select_one('link[rel="image_src"]') fails, an exception will be raised
        cover_soup = soup.select_one('link[rel="image_src"]')
        # if self.debug: self.log.info(self.who,"cover_soup prettyfied :\n", cover_soup.prettify()) # hide_it
        bbl_cover = cover_soup['href']

        if self.debug:
            self.log.info(self.who,'parse_cover() returns bbl_cover : ', bbl_cover)

        return bbl_cover

    def parse_meta(self, soup):
        '''
        get publisher, isbn ref, publication date from html part
        '''
        self.log.info("\n"+self.who,"in parse_meta(self, soup)")

      # if soup.select_one(".livre_refs.grey_light") fails it will produce an exception
      # note: when a class name contains white characters use a dot instead of the space
      # (blank means 2 subsequent classes for css selector)
        meta_soup = soup.select_one(".livre_refs.grey_light")
      # self.log.info(self.who,"meta_soup prettyfied :\n",meta_soup.prettify()) # hide_it

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
                # if self.debug: self.log.info(self.who,"tmp_pbdt : ", tmp_pbdt) # hide_it
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
        self.log.info("\n"+self.who,"in parse_tags(self, soup)")

      # if soup.select_one('.tags') fails it will produce an exception
        tag_soup=soup.select_one('.tags')
      # if self.debug: self.log.info(self.who,"tag_soup prettyfied :\n",tag_soup.prettify()) # hide_it
        tag_soup = soup.select_one('.tags').select('a')
        bbl_tags=[]
        for i in range(len(tag_soup)):
            tmp_tg = tag_soup[i].text.strip()
            bbl_tags.append(tmp_tg)

        bbl_tags = list(map(fixcase, bbl_tags))

        if self.debug:
                self.log.info(self.who,"parse_tags() return bbl_tags", bbl_tags)

        return bbl_tags
