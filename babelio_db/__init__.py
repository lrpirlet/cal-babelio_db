﻿#!/usr/bin/env python3
# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai
#

__license__   = 'GPL v3'
__copyright__ = '2021, Louis Richard Pirlet using VdF work as a base'
__docformat__ = 'restructuredtext en'

# those are python code that are directly available in calibre closed environment (test import... using calibre-debug)
import urllib                                   # to access the web
from bs4 import BeautifulSoup as BS             # to dismantle and manipulate HTTP (HyperText Markup Language)
#import sys                                      # so I can access sys (mainly during development, probably useless now)
import time                                     # guess that formats data and time in a common understanding
from queue import Empty, Queue                  # to submit jobs to another process (worker use it to pass results to calibre
from difflib import SequenceMatcher as SM
''' difflib has SequenceMatcher to compare 2 sentences
s1 = ' It was a dark and stormy night. I was all alone sitting on a red chair. I was not completely alone as I had three cats.'
s2 = ' It was a murky and stormy night. I was all alone sitting on a crimson chair. I was not completely alone as I had three felines.'
result = SM(None, s1, s2).ratio()
result is 0.9112903225806451... anything above .6 may be considered similar
'''

# the following make some calibre code available to my code
from calibre.ebooks.metadata.sources.base import (Source, Option)
from calibre.ebooks.metadata import check_isbn
from calibre.utils.icu import lower
from calibre.utils.localization import get_udc

def urlopen_with_retry(log, dbg_lvl, br, url, rkt, who):
    '''
    this is an attempt to keep going when the connection to the site fails for no (understandable) reason
    "return (sr, sr.geturl())" with sr.geturl() the true url address of sr (the content).
    '''
    debug=dbg_lvl & 4
    if debug:
        log.info(who, "In urlopen_with_retry(log, dbg_lvl, br, url, rkt, who)\n")

    tries, delay, backoff=4, 3, 2
    while tries > 1:
        try:
            sr = br.open(url,data=rkt,timeout=30)
            log.info(who,"(ret_soup) sr.getcode()  : ", sr.getcode())
            if debug:
                log.info(who,"url_vrai      : ", sr.geturl())
                log.info(who,"sr.info()     : ", sr.info())
            return (sr, sr.geturl())
        except urllib.error.URLError as e:
            if "500" in str(e):
                log.info("\n\n\n"+who,"HTTP Error 500 is Internal Server Error, sorry\n\n\n")
                raise Exception('(ret_soup) Failed while acessing url : ',url)
            else:
                log.info(who,"(urlopen_with_retry)", str(e),", will retry in", delay, "seconds...")
                time.sleep(delay)
                delay *= backoff
                tries -= 1
                if tries == 1 :
                    log.info(who, "exception occured...")
                    log.info(who, "code : ",e.code,"reason : ",e.reason)
                    raise Exception('(ret_soup) Failed while acessing url : ',url)

def ret_soup(log, dbg_lvl, br, url, rkt=None, who=''):
    '''
    Function to return the soup for beautifullsoup to work on. with:
    br is browser, url is request address, who is an aid to identify the caller
    rkt list of arguments for a POST request, if rkt is None, the request is GET
    return (soup, url_ret)
    '''
    debug=dbg_lvl & 4
    if debug:
        log.info(who, "In ret_soup(log, dbg_lvl, br, url, rkt=none, who=''\n")
        log.info(who, "br  : ", br)
        log.info(who, "url : ", url)
        log.info(who, "rkt : ", rkt)

  # Note: le SEUL moment ou on doit passer d'un encodage des charactères à un autre est quand on reçoit des donneées
  # d'un site web... tout, absolument tout, est encodé en uft_8 dans le plugin... J'ai vraiment peiné a trouver l'encodage
  # des charracteres qui venaient de noosfere... Meme le decodage automatique se plantait...
  # J'ai du isoler la création de la soup du decodage dans la fonction ret_soup().
  # variable "from_encoding" isolée pour trouver quel est l'encodage d'origine...
  #
  # from_encoding="windows-1252"

    log.info(who, "Accessing url : ", url)
    if rkt :
        log.info(who, "search parameters : ",rkt)
        rkt=urllib.parse.urlencode(rkt).encode('ascii')
        if debug: log.info(who, "formated parameters : ", rkt)

    resp = urlopen_with_retry(log, dbg_lvl, br, url, rkt, who)
    # if debug: log.info(who,"...et from_encoding, c'est : ", from_encoding)

    sr, url_ret = resp[0], resp[1]

    soup = BS(sr, "html5lib")       #, from_encoding=from_encoding) # needed when charset value is a lie
    if debug:
#        log.info(who,"soup.prettify() :\n",soup.prettify())               # très utile parfois, mais que c'est long...
        log.info(who,"(ret_soup) return (soup, sr.geturl()) from ret_soup\n")
    return (soup, url_ret)

def verify_isbn(log, dbg_lvl, isbn_str, who=''):
    '''
    isbn_str est brute d'extraction... la fonction renvoie un isbn correct ou "invalide"
    Notez qu'on doit supprimer les characteres de separation et les characteres restants apres extraction
    et que l'on traite un mot de 10 ou 13 characteres.

    isbn_str is strait from extraction... function returns an ISBN maybe correct ...or not
    Characters irrelevant to ISBN and separators inside ISBN must be removed,
    the resulting word must be either 10 or 13 characters long.
    '''
    debug=dbg_lvl & 4
    if debug:
        log.info(who,"\nIn verify_isbn(log, dbg_lvl, isbn_str)\n")
        log.info(who,"isbn_str         : ",isbn_str)

    for k in ['(',')','-',' ']:
        if k in isbn_str:
            isbn_str=isbn_str.replace(k,"")
    if debug:
        log.info("isbn_str cleaned : ",isbn_str)
        log.info("return check_isbn(isbn_str) from verify_isbn\n")
    return check_isbn(isbn_str)         # calibre does the check for me after cleaning...

def ret_clean_text(log, dbg_lvl, text, swap=False, who=''):
    '''
    for the site search to work smoothly, authors and title needs to be cleaned
    we need to remove non significant characters and remove useless space character...
    Calibre per default presents the author as "Firstname Lastname", cleaned to
    become "firstname lastname"  Noosfere present the author as "LASTNAME Firstname",
    let's get "Firstname LASTNAME" cleaned to "firstname lastname"
    '''
    debug=dbg_lvl & 4
    if debug:
        log.info(who,"\nIn ret_clean_txt(self, log, text, swap =",swap,")\n")
        log.info(who,"text         : ", text)

    for k in [',','.', ':','-',"'",'"','(',')']:             # yes I found a name with '(' and ')' in it...
        if k in text:
            text = text.replace(k," ")
    text=" ".join(text.split())

    if swap:
        if debug:
            log.info("swap name and surname")
        nom=prenom=""
        for i in range(len(text.split())):
            if (len(text.split()[i])==1) or (not text.split()[i].isupper()):
                prenom += " "+text.split()[i]
            else:
                nom += " "+text.split()[i]
        text=prenom+" "+nom
        if debug: log.info("text         : ", text)

    clntxt = lower(get_udc().decode(text))

    if debug:
        log.info("cleaned text : ", clntxt)
        log.info("return text from ret_clean_txt")

    return clntxt

class Babelio(Source):

    name = 'Babelio'
    description = 'Télécharge les métadonnées et couverture depuis Babelio.com'
    author = 'VdF'
    version = (3, 0, 0)
    minimum_calibre_version = (6, 3, 0)

    capabilities = frozenset(['identify', 'cover'])
    touched_fields = frozenset(['title', 'authors', 'identifier:isbn', 'identifier:babelio', 'language', 'rating',
                                'comments', 'publisher', 'pubdate', 'series', 'tags'])
    has_html_comments = False
    supports_gzip_transfer_encoding = True

    ID_NAME = 'bbl_id'
    BASE_URL = 'https://www.babelio.com'

  # configuration du plugin
  # Since the babelio_db is written in French for French talking poeple, I
  # took the liberty to write the following information in French.

    config_help_message = '<p>'+_(" Babelio est un réseau social dédié aux livres et aux lecteurs. Il permet de créer"
                                  " et d’organiser sa bibliothèque en ligne, d’obtenir des informations sur des oeuvres,"
                                  " de partager et d’échanger ses goûts et impressions littéraires avec d’autres lecteurs.<br><br>"
                                  " Il est a noter que certaines images de couvertures ne sont PAS localisée sur le site"
                                  " même de Babelio... des temps extrèmement longs peuvent en être engendré.<br><br>"
                                  " Notez qu'une requête qui génère plus de 12 resultats se verra tronquée à 12..."
                                  " Il est possible de modifier ce comportement, mais au risque d'être banni de Babelio..."
                                  " Je déconseille <strong>(vous êtes prévenus...)</strong>"
                                  )

    options = (
        Option(
               'debug_level',
               'number',
               7,
               _("Verbosité du journal, de 0 à 7"),                                                    # verbosity of the log
               _("Le niveau de verbosité:<br>"                                                         # the level of verbosity.
                 " O un minimum de rapport,<br>"                                                       # value 0 will output the minimum,
                 " 1 rapport étendu de __init__,<br>"                                                  # 1 debug messages of __init__
                 " 2 rapport étendu de worker,<br>"                                                    # 2 debug messages of worker
                 " 4 rapport étendu des annexes...<br>"                                                # 4 debug level of accessory code...
                 " La somme 3, 5 ou 7 peut être introduite, ainsi 7 donne un maximum de rapport.<br>"  # 3, 5 or 7 is the sum of the value defined above.
                 " Note: mettre la verbosité = 7 pour rapport d'erreur")            # In fact it is a bitwise flag spread over the last 3 bits of debug_level
               ),
        Option(
               'Cover_wanted',
               'bool',
               True,
               _("Authorize les couvertures vue sur Babelio"),
               _("Cochez cette case pour authoriser les couvertures vues sur Babelio (peut être long).")
            )
    )

    @property
    def dbg_lvl(self):
        x = getattr(self, 'dl', None)
        if x is not None:
            return x
        dl = self.prefs.get('debug_level', False)
        return dl

    @property
    def with_cover(self):
        x = getattr(self, 'wcover', None)
        if x is not None:
            return x
        wcover = self.prefs.get('Cover_wanted', False)
        return wcover

    def get_book_url(self, identifiers):
        '''
        get_book_url : used by calibre to convert the identifier to a URL...
        return an url if bbl_id exists and is valid.
        For this to work, we need to define or find the minimum info to build a relevant url.
        Today this seems to be: URL_BASE+"nom-de-l-auteur-le-titre-du-livre/<une serie de chiffres>"
        that is: BASE_URL + "/livres/" + bbl_id or just: https://www.babelio.com/livres/ + bbl_id
        example over an url :
        https://www.babelio.com/livres/Savater-Il-giardino-dei-dubbi-Lettere-tra-Voltaire-e-Caro/598832
        "https://www.babelio.com/livres/"+"Savater-Il-giardino-dei-dubbi-Lettere-tra-Voltaire-e-Caro/598832"

        '''
        bbl_id = identifiers.get('babelio', None)
        if bbl_id and "/" in bbl_id and bbl_id.split("/")[-1].isnumeric():
            return (self.ID_NAME, bbl_id, "https://www.babelio.com/livres/" + bbl_id)

    def id_from_url(self, url):
        '''
        id_from_url : takes an URL and extracts the identifier details...
        '''
        bbl_id = ""
        if "https://www.babelio.com/livres/" in url:
            bbl_id = url.replace("https://www.babelio.com/livres/","").strip()
        if "/" in bbl_id and bbl_id.split("/")[-1].isnumeric():
            return (self.ID_NAME, bbl_id)
        else:
            return None

    def create_query(self, log, title=None, authors=None):
        '''
        this returns an URL build with all the tokens made from both the title and the authors
        called by identify()
        '''
        debug=self.dbg_lvl & 1
        if debug:
            log.info('in create_query()\n')
            log.info('title       : ', title)
            log.info('authors     : ', authors)

        BASE_URL_FIRST = 'http://www.babelio.com/resrecherche.php?Recherche='
        BASE_URL_MID = '+'
        BASE_URL_LAST = "&amp;tri=auteur&amp;item_recherche=livres&amp;pageN=1"
        q = ''
        au = ''

        if authors:

            for i in range(len(authors)):
                authors[i] = ret_clean_text(log, self.dbg_lvl, authors[i])
                if "inconnu" in authors[i]:
                    authors[i] =""
# not sure whether or not this is a bug, in "get_author_tokens"... the net result is :
# the search gives a different result when authors[x] is blank or contains "Inconnu(e)"
# Seems confirmed try oedipe with authors field blank or with "Inconnu(e)"

            author_tokens = self.get_author_tokens(authors, only_first_author=True)
            au='+'.join(author_tokens)

        if title:
            title = ret_clean_text(log, 7, title)
            title_tokens = list(self.get_title_tokens(title, strip_joiners=False, strip_subtitle=True))
            q='+'.join(title_tokens)
        else:
    #    if not q:
            log.info("Pas de titre, semble-t-il... donc return None\n")
            return None

        log.info("return from create_query\n")
        return '%s%s%s%s%s'%(BASE_URL_FIRST,au,BASE_URL_MID,q,BASE_URL_LAST)

    def identify(self, log, result_queue, abort, title=None, authors=None, identifiers={}, timeout=30):
        '''
        this is the entry point...
        Note this method will retry without identifiers automatically... read can be resubmitted from inside it
        if no match is found with identifiers.
        '''
        log.info('-+-+-+-+-+-+-+-+-+-+ Entry point +-+-+-+-+-+-+-+-+-+-')
        log.info('self.with_cover : ', self.with_cover)
        log.info('self.dgb_lvl    : ', self.dbg_lvl)
        log.info('\nIn identify(self, log, result_queue, abort, title=.., authors=.., identifiers=.., timeout=30)\n')

        debug=self.dbg_lvl & 1
        if debug:
            log.info("title       : ", title)
            log.info("authors     : ", authors)
            log.info("identifiers : ", identifiers)
        query = None
        matches = []
        br = self.browser

      # on a des identifiers
        if identifiers:
          # En premier, on essaye de charger la page si un id babelio existe
            tmp_matches = self.get_book_url(identifiers)
            if tmp_matches:
                matches = [tmp_matches[2]]
                log.info("babelio identifier trouvé... pas de recherche sur babelio... on saute directement au livre")

          # ensuite, on essaye de charger la page si un ISBN existe
          # def verify_isbn(log, dbg_lvl, isbn_str, who=''):
            if not matches:
                isbn = check_isbn(identifiers.get('isbn', None))
                if isbn:
                    query= "https://www.babelio.com/resrecherche.php?Recherche=%s&item_recherche=isbn"%isbn
                    log.info("ISBN identifier trouvé, on cherche cet ISBN sur babelio : ", query)

          # Enfin sauf identifiers, on essaye auteur+titre ou même titre
          # mais titre doit exister
        if not matches:
            if not query:
                query = self.create_query(log, title=title, authors=authors)
                if query is None:
                    log.error('Métadonnées incorrecte ou insuffisantes pour la requête')
                    log.error("Verifier la validité des ids soumis (ISBN, babelio)")
                    log.error("ainsi que la bonne orthographe des auteurs et du titre")
                    return
                log.info('déduit du/des author/s et/ou du titre... on cherche sur babelio : ', query)

            soup=ret_soup(log, self.dbg_lvl, br, query)[0]

            self._parse_search_results(log, title, authors, matches, soup, br)
            if not len(matches):
                log.info("Pas de résultat avec l'ISBN, on recherche les auteurs et le titre.")
                return self.identify(log, result_queue, abort, title=title, authors=authors, timeout=timeout)

        if abort.is_set():
            if debug:
                log.info("abort is set...")
            return

        if not matches:
            if title and authors and len(authors) > 1:
                log.info('Pas de résultat avec tous les auteurs, on utilise uniquement le premier.')
                return self.identify(log, result_queue, abort, title=title, authors=[authors[0]], timeout=timeout)
            elif authors and len(authors) == 1 :
                log.info('Pas de résultat, on utilise uniquement le titre.')
                return self.identify(log, result_queue, abort, title=title, timeout=timeout)
            log.error('Pas de résultat pour la requête : ', query)
            return

        if debug: log.info(" matches : ", matches)
        if len(matches) > 12:       # protection to avoid banishment
            raise Exception('len(matches) still greater than 12... better stop than being stopped')

        from calibre_plugins.babelio.worker import Worker
        workers = [Worker(url, result_queue, br, log, i, self, self.dbg_lvl) for i, url in enumerate(matches)]

        for w in workers:
            w.start()
            time.sleep(0.1)         # Don't send all requests at the same time

        while not abort.is_set():   # sit and relax till all workers are done or aborted
            a_worker_is_alive = False
            for w in workers:
                w.join(0.1)
                if abort.is_set():
                    break
                if w.is_alive():
                    a_worker_is_alive = True
            if not a_worker_is_alive:
                break

        return None                 # job done

    def _parse_search_results(self, log, orig_title, orig_authors, matches, soup, br):
        '''
        this method returns after it modifies "matches" (or not) received as a parameter
        note: if several matches, the first presented in babelio will be the first in the
        matches list; it will be submited as the first worker... (highest priority)
        !! CAUTION !! if the number of book discovered is greater than 12, the first 3 found
        and 9 others picked at random will be set in matches
        '''
        log.info('In _parse_search_results(self, log, orig_title, orig_authors, matches, soup)')
        debug=self.dbg_lvl & 1
        if debug:
            log.info("(inutilisé) orig_title    : ", orig_title)
            log.info("(inutilisé) orig_authors  : ", orig_authors)
            log.info("matches                   : ", matches)

      #   <td class="titre_livre">
      #   est unique par livre correspondant à la recherche
      #   et sous cette ref <a class="titre_v2" ... donne les refs

      # there could be several matches just create a book with title "oedipe roi" and no author...
      # run edit metadata to find... a lot of possibilities... and get banned for a week because
      # too many hits in too short a time...

        count=0
        while count < 3 :                                                       # loop over first 3 pages (maximum)
            x=soup.select('.titre_v2')                                          #
            if len(x):                                                          # loop over all html addresses tied with titre_v2 (all book ref)
                for i in range(len(x)):                                         # !!CAUTION!! each page may have up to 10 books
                    y=Babelio.BASE_URL + x[i]["href"]                           #
                    if not y in matches: matches.append(y)                      # but do not duplicate with duplicated address for the cover image
            if not soup.select_one('.icon-next'):                               #
                break                                                           # exit loop if no more next page
            count = count + 1                                                   #
            nxtpg = Babelio.BASE_URL + soup.select_one('.icon-next')["href"]    # get next page adress
            if debug: log.info("next page : ",nxtpg)                            #
            soup=ret_soup(log, self.dbg_lvl, br, nxtpg)[0]                      # get new soup content and loop again
            time.sleep(0.2)                                                     # but wait a while so as not to hit www.babelio.com too hard

        if debug:
            log.info("matches at return time : ", matches)
            log.info("nombre de matches      : ", len(matches))

        if len(matches) > 12:           # if > 12, keep first 3, then remove randomly item greater than 4 till =12
            from random import randint
            log.info("\n+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-")
            log.info("nombre de matches      : ", len(matches))
            while len(matches) > 12:
                matches.remove(matches[randint(4,len(matches))-1])
            log.info("plus de 12 resultats... On ne considère que les 3 premiers résultats et 9 autres pris aléatoirement")
            log.info("+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-\n")
        return

    def get_cached_cover_url(self, identifiers):
        '''
        retrieve url address of the cover associated with NAME_id or ISBN
        '''
        if not self.with_cover:
            return None
        url = None
        bbl_id = identifiers.get('babelio', None)
        if bbl_id is None:
            isbn = identifiers.get('isbn', None)
            if isbn is not None:
                bbl_id = self.cached_isbn_to_identifier(isbn)
        if bbl_id is not None:
            url = self.cached_identifier_to_cover_url(bbl_id)
        return url

    def download_cover(self, log, result_queue, abort,
        title=None, authors=None, identifiers={}, timeout=30, get_best_cover=False):
        '''
        will download cover as directed by Babelio provided it was found (and then cached)...
        If not, it will run the metadata download and try to cache the cover URL...
        Note that the cover url may NOT be local to Babelio leading to possibly long
        waiting time and eventualy timeout
        '''
        debug=self.dbg_lvl & 1

        if debug: log.info("\n In download_cover ")

        if not self.with_cover:
            return
        cached_url = self.get_cached_cover_url(identifiers)
        if debug: log.info('cache :', cached_url)
        if cached_url is None:
            if debug: log.info('Pas de cache, on lance identify')
            rq = Queue()
            self.identify(log, rq, abort, title=title, authors=authors,
                    identifiers=identifiers)
            if abort.is_set():
                return
            results = []
            while True:
                try:
                    results.append(rq.get_nowait())
                except Empty:
                    break
            for mi in results:
                cached_url = self.get_cached_cover_url(mi.identifiers)
                if cached_url is not None:
                    break

        if cached_url is None:
            if debug: log.info('Pas de couverture trouvée.')
            return

        if abort.is_set():
            return

        br = self.browser
        if debug: log.info('On télécharge la couverture depuis :', cached_url)
        try:
            cdata = br.open_novisit(cached_url, timeout=timeout).read()
            result_queue.put((self, cdata))
        except:
            log.exception('Impossible de télécharger la couverture depuis :', cached_url)


####################### test section #######################

if __name__ == '__main__':

  # Run these tests from the directory containing all files needed for the plugin (the files that go into the zip file)
  # that is: __init__.py, plugin-import-name-babelio.txt and optional .py such as worker.py, ui.py, whatever...
  # from a terminal issue in sequence:
  # calibre-customize -b .
  # calibre-debug -e __init__.py
  # attention: on peut voir un message prévenant d'une erreur... en fait ce message est activé par la longueur du log... (parfois fort grand)
  # Careful, a message may pop up about an error... however this message pops up function of the length of the log... (sometime quite big)
  # anyway, verify... I have been caught at least once

    from calibre.ebooks.metadata.sources.test import (test_identify_plugin, title_test, authors_test, series_test)

    test_identify_plugin(Babelio.name,
        [
            ( # A book with ISBN specified, ISBN not found in babelio, expect some report about missing series
                {'identifiers':{'isbn': '9781846148200'}, 'title':'Limonov', 'authors':['Emmanuel Carrère']},
                [title_test("Limonov", exact=False), authors_test(['Emmanuel Carrère'])]
            ),

            ( # A book with ISBN specified
                {'identifiers':{'isbn': '2-266-03441-3'}, 'title':'Futurs sans escale', 'authors':['ANTHOLOGIE']},
                [title_test("Futurs sans escale", exact=True), authors_test(['ANTHOLOGIE']), series_test('Isaac Asimov présente',1)]
            ),

            # ( # A book with ISBN specified
            #     {'identifiers':{'isbn': '2-265-04038-X'}, 'title':'Onze bonzes de bronze', 'authors':['Max ANTHONY']},
            #     [title_test("Onze bonzes de bronze", exact=True), authors_test(['Max ANTHONY']), series_test('Ned Lucas',1)]
            # ),

            # ( # A book with nsfr_id:bk$5308$vl$-323559
            #     {'identifiers':{'nsfr_id':'bk$5308$vl$-323559'}, 'title':"Le Printemps d'Helliconia", 'authors':['B.W. Aldiss']},
            #     [title_test("Le Printemps d'Helliconia", exact=True), authors_test(['Brian Aldiss']), series_test('Helliconia', 1.0)]
            # ),

            # ( # A book with a wrong ISBN and title not quite right, will find one correct and 3 incorrect, correct is hightest priority...
            #     {'identifiers':{'isbn': '227721409x'}, 'title':"La Patrouille des temps", 'authors':['Poul Anderson']},
            #     [title_test("La Patrouille du temps", exact=True), authors_test(['Poul Anderson']), series_test('La Patrouille du Temps', 1.0)]
            # ),

##            ( # A book with no ISBN specified ... will fail over serie (serie is missing...)
##                {'identifiers':{}, 'title':"La Guerre contre le Rull", 'authors':['A.E. van Vogt']},
##                [title_test("La Guerre contre le Rull", exact=True), authors_test(['Alfred Elton VAN VOGT']), series_test('',0)]
##            ),

##            ( # A book with a HTTP Error 500
##                {'identifiers':{'isbn': '2-290-04457-1'}, 'title':"Le Monde de l'exil", 'authors':['David BRIN']},
##                [title_test("Le Monde de l'exil", exact=True), authors_test(['David Brin']), series_test('', 0)]
##            ),

        ])
