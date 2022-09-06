﻿#!/usr/bin/env python3
# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai
#
# Ce travail basé sur celui de VdF pour babelio est entrepris pour essayer de resoudre les multiples petits problèmes
# que je rencontre...
#
#y pas de reference ni de moyen d'ajouter un id...
#   get_book_url : used by calibre to convert the identifier to a URL...
#   id_from_url : takes an URL and extracts the identifier details...
#
# dès que le contenu de babelio est remonté, TOUTE l'information est traduite en utf8
# TOUT les outputs (logs...) et les inputs (what is read in the site...) sont en utf8...
# les multiples conversions rendent le code confus
#
# il est besoin de lancer des POST request pour chercher la suite du resumé (ref: "voir plus" dans certains livres)
#
# la compatibilité avec python 2.x me semble obsolete et perturbant.
#
# Identify devrait etre invoque avec NAME_ID then ISBN et si ça marche pas avec titre + auteur
#
# un config.py est ok mais je préfère utiliser le config integré, bien suffisant.
#
# Ce travail effectué, je ferai parvenir à VdF les sources... Il pourrait, si il veut, ameliorer sa version
# Sauf avis contraire de VdF, je ne publierai pas ce site sur calibre... même si il restera visible sur github
#

from __future__ import (unicode_literals, division, absolute_import,
                        print_function)
import six

__license__ = 'GPL v3'
__copyright__ = '2014, VdF>'
__docformat__ = 'restructuredtext'

import time, http.cookiejar, unicodedata
from six.moves.urllib.parse import quote
from six.moves.queue import Queue, Empty
from urllib.parse import quote, unquote
from queue import Queue, Empty
from difflib import SequenceMatcher
from lxml.html import fromstring, tostring

from calibre.ebooks.metadata import check_isbn
from calibre.ebooks.metadata.sources.base import Source
from calibre.utils.cleantext import clean_ascii_chars
from calibre.utils.config import JSONConfig

################# lrp
__license__   = 'GPL v3'
__copyright__ = '2021, Louis Richard Pirlet'
__docformat__ = 'restructuredtext en'           # whatever that means???

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
    '''
    debug=dbg_lvl & 4
    if debug:
        log.info(who, "In urlopen_with_retry(log, dbg_lvl, br, url, rkt, who)")

    tries, delay, backoff=4, 3, 2
    while tries > 1:
        try:
            sr = br.open(url,data=rkt,timeout=30)
            log.info(who,"(ret_soup) sr.getcode()  : ", sr.getcode())
            if debug:
                log.info(who,"url_vrai      : ", sr.geturl())
                log.info(who,"sr.info()     : ", sr.info())
                log.info(who,"ha ouais, vraiment? charset=iso-8859-1... ca va mieux avec from_encoding...")
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
    Function to return the soup for beautifullsoup to work on.
    '''
    debug=dbg_lvl & 4
    if debug:
        log.info(who, "In ret_soup(log, dbg_lvl, br, url, rkt=none, who='[__init__]')")
        log.info(who, "br  : ", br)
        log.info(who, "url : ", url)
        log.info(who, "rkt : ", rkt)

  # Note: le SEUL moment ou on doit passer d'un encodage des characteres a un autre est quand on reçoit des donneées
  # d'un site web... tout, absolument tout, est encodé en uft_8 dans le plugin... J'ai vraiment peiné a trouver l'encodage
  # des charracteres qui venaient de noosfere... Meme le decodage automatique se plantait...
  # J'ai du isoler la création de la soup du decodage dans la fonction ret_soup().
  # variable "from_encoding" isolée pour trouver quel est l'encodage d'origine...
  #
  # variable "from_encoding" isolated to find out what is the site character encoding... The announced charset is WRONG
  # Even auto decode did not always work... I knew that my setup was wrong but it took me a while...
  # Maybe I should have tried earlier the working solution as the emitting node is MS
  # (Thanks MS!!! and I mean it as I am running W10.. :-) but hell, proprietary standard is not standard)...
  # It decode correctly to utf_8 with windows-1252 forced as from_encoding
    from_encoding="windows-1252"

    log.info(who, "Accessing url : ", url)
    if rkt :
        log.info(who, "search parameters : ",rkt)
        rkt=urllib.parse.urlencode(rkt).encode('ascii')
        if debug: log.info(who, "formated parameters : ", rkt)

    resp = urlopen_with_retry(log, dbg_lvl, br, url, rkt, who)
    if debug: log.info(who,"...et from_encoding, c'est : ", from_encoding)

    sr, url_ret = resp[0], resp[1]

    soup = BS(sr, "html5lib", from_encoding=from_encoding)
    if debug:
#        log.info(who,"soup.prettify() :\n",soup.prettify())               # très utile parfois, mais que c'est long...
        log.info(who,"(ret_soup) return (soup,sr.geturl()) from ret_soup\n")
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
        log.info("\nIn verify_isbn(log, dbg_lvl, isbn_str)")
        log.info("isbn_str         : ",isbn_str)

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
    we need to remove non significant characters and remove useless space character
    '''
    debug=dbg_lvl & 4
    if debug:
        log.info("\nIn ret_clean_txt(self, log, text, swap =",swap,")")
        log.info("text         : ", text)

  # Calibre per default presents the author as "Firstname Lastname", cleaned to be become "firstname lastname"
  # Noosfere present the author as "LASTNAME Firstname", let's get "Firstname LASTNAME" cleaned to "firstname lastname"
    for k in [',','.','-',"'",'"','(',')']:             # yes I found a name with '(' and ')' in it...
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

    if debug:
        log.info("cleaned text : ", text)
        log.info("return text from ret_clean_txt")

    return lower(get_udc().decode(text))

################# lrp

class Babelio(Source):

    name = 'Babelio'
    description = 'Télécharge les métadonnées et couverture depuis Babelio.com'
    author = 'VdF'
    version = (2, 0, 0)
    minimum_calibre_version = (6, 3, 0)

    capabilities = frozenset(['identify', 'cover'])
    touched_fields = frozenset(['title', 'authors', 'identifier:isbn', 'identifier:babelio', 'language', 'rating',
                                'comments', 'publisher', 'pubdate', 'tags'])
    has_html_comments = False
    supports_gzip_transfer_encoding = True
    BASE_URL = 'https://www.babelio.com'

    print(('BASE_URL 4 %s' %BASE_URL))

    def config_widget(self):
        print('config widget')
        from calibre_plugins.babelio.config import ConfigWidget
        return ConfigWidget(self)

    print('config widget')

    def create_query(self, log, title=None, authors=None, identifiers={}):
        '''
        this returns an URL build with all the tokens made from both the title and the authors
        called by identify()
        '''
        debug = 1
        if debug:
            log.info('\nin create_query()')
            log.info('title       : ', title)
            log.info('authors     : ', authors)
            log.info('identifiers : ', identifiers)

        BASE_URL_FIRST = 'http://www.babelio.com/resrecherche.php?Recherche='
        BASE_URL_MID = '+'
        BASE_URL_LAST = '&page=1&item_recherche=livres&tri=auteur'
        q = ''
        au = ''
        isbn = check_isbn(identifiers.get('isbn', None))
        tokens = []
        title = title.replace('\'é','\'e')
        title = title.replace('\'è','\'e')
        title = title.replace('\'ê','\'e')
        title = title.replace('\'É','\'e')
        title = title.replace('\'â','\'a')
        title = title.replace('\'à','\'a')
        title = title.replace('\'î','\'i')
        title = title.replace('\œ','oe')

        if title:
            title_tokens = list(self.get_title_tokens(title, strip_joiners=False, strip_subtitle=True))
            q='+'.join(title_tokens)
# lrp ... keep utf8
#             if title_tokens:
#                 try:
#                     tokens = [quote(t.encode('iso-8859-1') if isinstance(t, str) else t) for t in title_tokens]
#                     q='+'.join(tokens)
#                 except:
#                    return None

        if authors:
            author_tokens = self.get_author_tokens(authors, only_first_author=True)
            au='+'.join(author_tokens)
# lrp ... keep utf8
#             if author_tokens:
#                 #except UnicodeEncodError 'iso-8859-1' codec
#                 try:
#                     tokens = [quote(t.encode('iso-8859-1') if isinstance(t, str) else t) for t in author_tokens]
#                     au='+'.join(tokens)
#                 except:
#                     return None

        if not q:
            log.info("Pas de titre, semble-t-il... return\n")
            return None

        log.info("return from create_query\n")
        return '%s%s%s%s%s'%(BASE_URL_FIRST,au,BASE_URL_MID,q,BASE_URL_LAST)

#    print('create query')

    def identify(self, log, result_queue, abort, title=None, authors=None, identifiers={}, timeout=30):
        '''
        this is the entry point...
        Note this method will retry without identifiers automatically... read can be resubmitted from inside it
        if no match is found with identifiers.
        '''
        debug=1
        if debug:
            log.info("\nIn identify(self, log, result_queue, abort, title=None, authors=None, identifiers={}, timeout=30)")
            log.info("abort       : ", abort)
            log.info("title       : ", title)
            log.info("authors     : ", authors)
            log.info("identifiers : ", identifiers)

        # lrp recherche isbn https://www.babelio.com/resrecherche.php?Recherche=9782823809756&item_recherche=isbn
        # lrp recherche token

        matches = []
        br = self.browser
        cj = http.cookiejar.LWPCookieJar()
        br.set_cookiejar(cj)
        log.info('avant query')
        query = self.create_query(log, title=title, authors=authors, identifiers=identifiers)
        log.info('returned query is %s' %query)
        if query is None:
            log.error('Métadonnées insuffisantes pour la requête'.encode('latin-1'))
            return

        #log.info(b'Recherche de : %s' % unquote(query).encode('latin-1'))

        log.info('Recherche de : %s' % unquote(query))
        response = br.open_novisit(query, timeout=timeout)
        try:
            raw = response.read().strip()
            raw = raw.decode('latin-1', errors='replace')
            #open('E:\\babelio.html', 'wb').write(raw)
            if not raw:
#                 log.error('Pas de résultat pour la requête : %r'.encode('latin-1') % unquote(query).encode('latin-1'))
                log.error('Pas de résultat pour la requête : ', query)
                return
            root = fromstring(clean_ascii_chars(raw))
        except:
            msg = 'Impossible de parcourir la page babelio avec la requête : %r'.encode('latin-1') % unquote(query).encode('latin-1')
            log.exception(msg)
            return msg
        self._parse_search_results(log, title, authors, root, matches, timeout)

        if abort.is_set():
            if debug:
                log.info("abort is set...")
            return

        if not matches:
            if title and authors and len(authors) > 1:
#                 log.info('Pas de résultat avec les auteurs, on utilise uniquement le premier.'.encode('latin-1'))
                log.info('Pas de résultat avec les auteurs, on utilise uniquement le premier.')
                return self.identify(log, result_queue, abort, title=title,
                        authors=[authors[0]], timeout=timeout)
            elif authors and len(authors) == 1 :
#                 log.info('Pas de résultat, on utilise uniquement le titre.'.encode('latin-1'))
                log.info('Pas de résultat, on utilise uniquement le titre.')
                return self.identify(log, result_queue, abort, title=title, timeout=timeout)
#             log.error('Pas de résultat pour la requête : %r'.encode('latin-1') % unquote(query.encode('latin-1')))
            log.error('Pas de résultat pour la requête : ', query)
            return

        from calibre_plugins.babelio.worker import Worker
        workers = [Worker(url, result_queue, br, log, i, self) for i, url in
                enumerate(matches)]

        for w in workers:
            w.start()
            # Don't send all requests at the same time
            time.sleep(0.1)

        while not abort.is_set():
            a_worker_is_alive = False
            for w in workers:
                w.join(0.1)
                if abort.is_set():
                    break
                if w.is_alive():
                    a_worker_is_alive = True
            if not a_worker_is_alive:
                break

        return None

    def _parse_search_results(self, log, orig_title, orig_authors, root, matches, timeout):
        '''
        this method returns after it modifies "matches" received as a parameter
        '''
        debug = 1
        if debug:
            log.info("(inutilisé) orig_title : ", orig_title)
            log.info("orig_authors           : ", orig_authors)
            log.info("root                   : ", root)
            log.info("matches                : ", matches)

        orig_aut = None
        if orig_authors is not None:
            orig_aut = [author.split(',')[0] for author in orig_authors if (',' in author)] \
                        + [author.split(' ')[1] for author in orig_authors if (' ' in author)]
        # log.info([author.split(',')[0] for author in orig_authors if (',' in author)])
        # log.info([author.split(' ')[1] for author in orig_authors if (' ' in author)])
        non_trouve = root.xpath('//div[@class="module_t1"]/h2')
        '''if non_trouve :
            non_trouve_text = non_trouve[0].text_content()
            if '(0)' in non_trouve_text :
                return'''

        def minussa(chaine):
            chaine = str(chaine.lower())
            chnorm = unicodedata.normalize('NFKD', chaine)
            return "".join([car for car in chnorm if not unicodedata.combining(car)])

        def simil(mot1, mot2, ratio):
            mot1, mot2 = minussa(mot1), minussa(mot2)
            return SequenceMatcher(None, mot1, mot2).ratio() >= ratio

        def is_simil(orig_aut, dict_res, ratio):
            for aut_compl in (v.text for v in list(dict_res.values())) :
                for a in orig_aut :
                    if simil(aut_compl.split()[-1], a, ratio):
                        return True
                    return False

        titre_res = root.xpath(".//*[@id='page_corps']/div/div[4]/div[2]/table/tbody/tr/td[2]/a[1]")
        log.info('t_res', titre_res)
        if len(titre_res) == 0 :
            return
        else :
            matches.append(Babelio.BASE_URL + titre_res[0].get('href'))
            return
# lrp never accessed
        # aut_res = root.xpath(".//*[@id='page_corps']/div/div[4]/div[2]/table/tbody/tr/td[3]/a")
        # dict_res = dict(list(zip(titre_res, aut_res)))
        # # log.info('dict', dict_res)
        # if orig_aut is not None :
        #     ratio = 0.7
        #     for k in list(dict_res.keys()):
        #         if is_simil(orig_aut, dict_res, ratio):
        #             matches.append(Babelio.BASE_URL + k.get('href'))
        # else :
        #     for i in range(0, len(titre_res)):
        #         matches.append(Babelio.BASE_URL + titre_res[i].get('href'))
        #         matches = matches[:5]
        # log.info('mat', matches)

    def get_cached_cover_url(self, identifiers):
        if JSONConfig('plugins/Babelio').get('cover', False) == False:
            return None
        url = None
        bab_id = identifiers.get('babelio', None)
        if bab_id is None:
            isbn = identifiers.get('isbn', None)
            if isbn is not None:
                bab_id = self.cached_isbn_to_identifier(isbn)
        if bab_id is not None:
            url = self.cached_identifier_to_cover_url(bab_id)
        return url

    def download_cover(self, log, result_queue, abort,
        title=None, authors=None, identifiers={}, timeout=30, get_best_cover=False):
        if JSONConfig('plugins/Babelio').get('cover', False) == False:
            return
        cached_url = self.get_cached_cover_url(identifiers)
        log.info('cache :', cached_url)
        if cached_url is None:
            log.info('Pas de cache, on lance identify')
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
            # results.sort(key=self.identify_results_keygen(
                # title=title, authors=authors, identifiers=identifiers))
            for mi in results:
                cached_url = self.get_cached_cover_url(mi.identifiers)
                if cached_url is not None:
                    break
        if cached_url is None:
#             log.info('Pas de couverture trouvée.'.encode('latin-1'))
            log.info('Pas de couverture trouvée.')
            return

        if abort.is_set():
            return
        br = self.browser

#         log.info('On télécharge la couverture depuis :'.encode('latin-1'), cached_url)
        log.info('On télécharge la couverture depuis :', cached_url)
        try:
            cdata = br.open_novisit(cached_url, timeout=timeout).read()
            result_queue.put((self, cdata))
        except:
#             log.exception('Impossible de télécharger la couverture depuis :'.encode('latin-1'), cached_url)
            log.exception('Impossible de télécharger la couverture depuis :', cached_url)

