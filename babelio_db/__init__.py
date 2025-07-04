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
import time, datetime                           #
from queue import Empty, Queue                  # to submit jobs to another process (worker use it to pass results to calibre
from difflib import SequenceMatcher as SM
''' difflib has SequenceMatcher to compare 2 sentences
s1 = ' It was a dark and stormy night. I was all alone sitting on a red chair. I was not completely alone as I had three cats.'
s2 = ' It was a murky and stormy night. I was all alone sitting on a crimson chair. I was not completely alone as I had three felines.'
result = SM(None, s1, s2).ratio()
result is 0.9112903225806451... anything above .6 may be considered similar
'''

import tempfile, os, contextlib

# the following makes some calibre code available to my code
from calibre.ebooks.metadata.sources.base import (Source, Option)
from calibre.ebooks.metadata import check_isbn
from calibre.ebooks.metadata.sources.search_engines import rate_limit
from calibre.utils.icu import lower
from calibre.utils.localization import get_udc

TIME_INTERVAL = 1.2      # this is the minimum interval between 2 access to the web (with decorator on ret_soup())
LOCK_FILE = os.path.join(tempfile.gettempdir(), 'Babelio_dbpleaseabortworker.tmp')
LOCK_TIME = datetime.timedelta(hours = 23)        # use "minutes = 10"

      # The kludge below (lockfile in the temp directory) is an attempt to get a message from an instance of the worker.
      # If a worker crash because returned url in NOT the requested url then I want to stop poking babelio for 23 hours.
      # The crashing worker will create a temporary lockfile named Babelio_dbpleaseabortworker.tmp,
      # ret_soup() will monitor the presence of this lockfile and disalow any further access to babelio.
      # Now, this works well because of the class Un_par_un(): all requests are serialised with TIME_INTERVAL in between.
      #
      # before doing anything, delete the worker lockfile if it exist and was last modified 23 hours ago
      # the lockfile will be created as soon as a wrong returned url shows up,
      # preventing overwrite of calibre with wrong data AND protecting Babelio site from any further access
      #

with contextlib.suppress(FileNotFoundError):
    if datetime.datetime.now() - datetime.datetime.fromtimestamp(os.path.getmtime(LOCK_FILE)) > LOCK_TIME :
        os.remove(LOCK_FILE)

class Un_par_un(object):
    '''
    This is a class decorator, cause I am too lazy rewrite that plugin... :),
    beside I want to learn creating one. Well, granted, dedicated to ret_soup()

    Purpose: execute the decorated function with a minimum of x seconds
    between each execution, and collect all access time information...

    rate_limit() from calibre.ebooks.metadata.sources.search_engines provides the delay
    using a locked file containing the access time... maintenance of this resource
    is hidden in a context manager implementation.

    @contextmanager
    def rate_limit(name='test', time_between_visits=2, max_wait_seconds=5 * 60, sleep_time=0.2):

    I assume that calibre will wait long enough for babelio plugin (I pushed to 45 sec after first match)
    '''
    def __init__(self,fnctn):
        self.function = fnctn
        self._memory = []

    def __call__(self, *args, **kwargs):
      # who is calling
        who = "[__init__]"
        for key,value in kwargs.items():
            if "who" in key: who = value
        with rate_limit(name='Babelio_db', time_between_visits=TIME_INTERVAL):
          # call decorated function: "ret_soup" whose result is (soup,url)
            result = self.function(*args, **kwargs)
            self._memory.append((result[1], time.asctime(), who))
            return result

    def get_memory(self):
        mmry = self._memory
        self._memory = []
        return mmry

def urlopen_with_retry(log, dbg_lvl, br, url, rkt, who=''):
    '''
    this is an attempt to keep going when the connection to the site fails for no (understandable) reason
    "return (sr, sr.geturl())" with sr.geturl() the true url address of sr (the content).
    this will issue an exception on url_vrai is not equal to url, on response = 500
    '''
    debug=dbg_lvl & 4
    if debug:
        log.info(who, "In urlopen_with_retry(log, dbg_lvl, br, url, rkt={}, who={})\n".format(rkt,who))

    tries, delay, backoff=4, 3, 2
    while tries > 1:
        try:
            sr = br.open(url,data=rkt,timeout=30)
            url_vrai, info, code = sr.geturl(), sr.info(), sr.getcode()
            log.info(who,"(urlopen_with_retry) sr.getcode()  : ", code)

          # compare expected url with returned url, kill the worker if different to avoid corrupting calibre
          # the exception is the cleanest way to kill the worker
            if SM(None, url_vrai, url).ratio() < 0.7:
            # if sr.geturl() == 'https://www.babelio.com/livres/Fabre-Photos-volees/615123':  # for debug purpose raise exception on equal
                log.info("\n"+who,"returned url irs NOT requested url\n")
                log.info(who,"requested url  : ", url)
                log.info(who,"received url   : ", url_vrai)
                log.info(who,"returned code : ", code)
                log.info(who,"collected info :\n", info, '\n\n')

              # The kludge...
              # before crashing, let's create the file
                log.info(who,"open ", LOCK_FILE)
                log.info("\n"+who,"L'exception qui suit est voulue pour éviter de modifier Calibre\n")
                open(LOCK_FILE,'a')
                raise Exception(f'( requested url: {url}\nis not at all returned url: {sr.geturl()}')

            if debug:
                log.info(who,"url_vrai      : ", url_vrai)
                log.info(who,"sr.info()     : ", info)

            return (sr, sr.geturl())
        except urllib.error.URLError as e:
            if "500" in str(e):
                log.info("\n\n\n"+who,"HTTP Error 500 is Internal Server Error, sorry\n\n\n")
                raise Exception('(urlopen_with_retry) Failed while acessing url : ',url)
            else:
                log.info(who,"(urlopen_with_retry)", str(e),", will retry in", delay, "seconds...")
                time.sleep(delay)
                delay *= backoff
                tries -= 1
                if tries == 1 :
                    log.info(who, "exception occured...")
                    log.info(who, "code : ",e.code,"reason : ",e.reason)
                    raise Exception('(urlopen_with_retry) Failed while acessing url : ',url)

@Un_par_un
def ret_soup(log, dbg_lvl, br, url, rkt=None, who=''):
    '''
    Function to return the soup for beautifullsoup to work on. with:
    br is browser, url is request address, who is an aid to identify the caller,
    Un_par_un introduce a wait time to avoid DoS attack detection, rkt is the
    arguments for a     POST request, if rkt is None, the request is GET...
    return (soup, url_ret)
    '''
    debug=dbg_lvl & 4
    debugt=dbg_lvl & 8
    if debug or debugt:
        log.info(who, "In ret_soup(log, dbg_lvl, br, url, rkt={}, who={})\n".format(rkt, who))
        log.info(who, "URL request time : ", datetime.datetime.now().strftime("%H:%M:%S"))
    start = time.time()
    if debug:
        log.info(who, "br                : ", br)
        log.info(who, "url               : ", url)
        log.info(who, "rkt               : ", rkt)

    log.info(who, "Accessing url     : ", url)
    if rkt :
        log.info(who, "search parameters : ",rkt)
        rkt=urllib.parse.urlencode(rkt).encode('ascii')
        if debug: log.info(who, "formated parameters : ", rkt)

    resp = urlopen_with_retry(log, dbg_lvl, br, url, rkt, who)
    sr, url_ret = resp[0], resp[1]
    soup = BS(sr, "html5lib")

    # if debug: log.info(who,"soup.prettify() :\n",soup.prettify())               # hide_it # très utile parfois, mais que c'est long...
    return (soup, url_ret)

def verify_isbn(log, dbg_lvl, isbn_str, who=''):
    '''
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
        log.info(who,"isbn_str cleaned : ",isbn_str)
        log.info(who,"return check_isbn(isbn_str) from verify_isbn\n")
    return check_isbn(isbn_str)         # calibre does the check for me after cleaning...

def ret_clean_text(log, dbg_lvl, text, who=''):
    '''
    For the site search to work smoothly, authors and title needs to be cleaned.
    we need to remove non significant characters and remove useless space character...
    '''
    debug=dbg_lvl & 4
    if debug:
        log.info(who,"\nIn ret_clean_txt(self, log, text, who='')\n")
        log.info(who,"text         : ", text)

    txt = lower(get_udc().decode(text))

    for k in [',','.', ':','-',"'",'"','(',')','<','>','/']:             # yes I found a name with '(' and ')' in it...
        if k in txt:
            txt = txt.replace(k," ")
    clntxt=" ".join(txt.split())

    if debug:
        log.info(who,"cleaned text : ", clntxt)
        log.info(who,"return text from ret_clean_txt")

    return clntxt

class Babelio(Source):

    name                    = 'Babelio_db'
    description             = _('Downloads metadata and covers from www.babelio.com')
    author                  = '2021, Louis Richard Pirlet using VdF work as a base'
    version                 = (0, 8, 8)
    minimum_calibre_version = (6, 3, 0)

    capabilities = frozenset(['identify', 'cover'])
    touched_fields = frozenset(['title', 'authors', 'identifier:isbn', 'identifier:babelio_db',
                                'language', 'rating', 'comments', 'publisher', 'pubdate', 'series', 'tags'])
    has_html_comments = True        # quand les commentaires sont formatés html
    supports_gzip_transfer_encoding = True

    ID_NAME = 'babelio_id'
    BASE_URL = 'https://www.babelio.com'

  # configuration du plugin
  # Since the babelio_db is written in French for French talking poeple, I
  # took the liberty to write the following information in French.

    config_help_message = '<p>'+_(" Babelio est un réseau social dédié aux livres et aux lecteurs. Il permet de créer"
                                  " et d’organiser sa bibliothèque en ligne, d’obtenir des informations sur des oeuvres,"
                                  " de partager et d’échanger ses goûts et impressions littéraires avec d’autres lecteurs.<br>"
                                  " Il est à noter que certaines images de couvertures ne sont PAS localisées sur le site"
                                  " même de Babelio... des temps extrêmement longs peuvent en être engendré.<br><br>"
                                  " J'ai décidé d'éviter de charger plus d'une page de recherche pour essayer d'éviter le"
                                  " bannissement. Cela signifie trouver un maximum de 10 livres similaires en comptant sur Babelio"
                                  " pour trier les références les plus pertinentes.<br>"
                                  " Dans cette même veine, utiliser en même temps les plugins babelio et babelio_db est un moyen"
                                  " certain de provoquer trop de requêtes vers babelio.com..."
                                  ' et donc être perçu comme une "DoS attack"...<br>'
                                  " <em>Je déconseille... <strong>(Vous êtes prévenus...)</strong></em>"
                                  )

    options = (
        Option(
               'debug_level',
               'number',
               3,
               _("Verbosité du journal, de 0 à 15"),                            # verbosity of the log
               _("Le niveau de verbosité:<br>"                                  # the level of verbosity.
                 " O un minimum de rapport,<br>"                                # value 0 will output the minimum,
                 " 1 rapport étendu de __init__,<br>"                           # 1 debug messages of __init__
                 " 2 rapport étendu de worker,<br>"                             # 2 debug messages of worker
                 " 4 rapport étendu des annexes...<br>"                         # 4 debug level of accessory code...
                 " 8 rapport de timing... <br>"                                 # 8 debug level for timing
                 " Une somme peut être introduite, tel que 11 (__init__ et worker et timing)."
                 " Ainsi 11 donne les information de __init__, worker et timming...<br>"             # 3, 5 or 7 is the sum of the value defined above.
                 " Note: mettre la verbosité = 15 (maximum d'information) pour rapport d'erreur")    # In fact it is a bitwise flag spread over the last 4 bits of debug_level
        ),
        Option(
                'Cover_wanted',
                'bool',
                False,
                _("Autorise les couvertures vues sur Babelio"),
                _("Cochez cette case pour autoriser les couvertures vues sur Babelio (peut être long). "
                  "Attention, calibre rapporte: Impossible de trouver une couverture pour <titre>... "
                  "Ce n'est pas une erreur.")
        ),
        Option(
                'Pretty_wanted',
                'bool',
                False,
                _('Autorise un commentaire étendu'),
                _('Cochez cette case pour autoriser la référence, le titre "Résumé" et le titre "Popularité" dans les commentaires')
        ),
        Option(
                'Detailled_Rating_wanted',
                'bool',
                False,
                _('Autorise un rapport plus détaillé de la notation, si le commentaire étendu est sélectionné.'),
                _('Cochez cette case pour autoriser le titre "Popularité" dans les commentaires')
        ),
        Option(
                'tag_genre_combien',
                'number',
                12,
                _('Nombre de niveaux de pertinance des étiquettes de genre (roman, polar, poésie) '),
                _("La pertinence des étiquettes rouges foncés qui désignent le genre ou la forme de l'ouvrage détermine leur taille. "
                 "Les étiquettes sont triées par pertinence, plusieurs etiquettes peuvent avoir la même pertinence. "
                 "Le nombre introduit détermine combien de niveaux de pertinence seront obtenus à partir du niveau le plus élevé. "
                 "Ainsi la valeur 0 ne donne aucune etiquettes, 2 donne toutes les etiquettes des 2 plus haut niveaux.")
        ),
        Option(
                'tag_theme_combien',
                'number',
                12,
                _('Nombre de niveaux de pertinance des étiquettes thématiques (enfance, légendes arthuriennes, mafia etc.)'),
                _("La pertinence des étiquettes beiges clairs qui désignent le thème ou le sujet de l'ouvrage détermine leur taille. "
                 "Les étiquettes sont triées par pertinence, plusieurs etiquettes peuvent avoir la même pertinence. "
                 "Le nombre introduit détermine combien de niveaux de pertinence seront obtenus à partir du niveau le plus élevé. "
                 "Ainsi la valeur 0 ne donne aucune etiquettes, 2 donne toutes les etiquettes des 2 plus haut niveaux.")
        ),
        Option(
                'tag_lieu_combien',
                'number',
                12,
                _('Nombre de niveaux de pertinance des étiquettes de lieu (ou? : auteur britannique, Canada etc.)'),
                _("La pertinence des étiquettes oranges relative à l'origine géographique, le pays détermine leur taille. "
                 "Les étiquettes sont triées par pertinence, plusieurs etiquettes peuvent avoir la même pertinence. "
                 "Le nombre introduit détermine combien de niveaux de pertinence seront obtenus à partir du niveau le plus élevé. "
                 "Ainsi la valeur 0 ne donne aucune etiquettes, 2 donne toutes les etiquettes des 2 plus haut niveaux.")
        ),
        Option(
                'tag_quand_combien',
                'number',
                12,
                _('Nombre de niveaux de pertinance des étiquettes relatives à une période (Quand? : 19ème siècle, médiéval) '),
                _("La pertinence des étiquettes vert lichen relatives à une période détermine leur taille. "
                 "Les étiquettes sont triées par pertinence, plusieurs etiquettes peuvent avoir la même pertinence. "
                 "Le nombre introduit détermine combien de niveaux de pertinence seront obtenus à partir du niveau le plus élevé. "
                 "Ainsi la valeur 0 ne donne aucune etiquettes, 2 donne toutes les etiquettes des 2 plus haut niveaux.")
        )
    )

    @property
    def dbg_lvl(self):
        x = getattr(self, 'wdl', None)
        if x is not None:
            return x
        wdl = self.prefs.get('debug_level', False)
        return wdl

    @property
    def with_cover(self):
        x = getattr(self, 'wcover', None)
        if x is not None:
            return x
        wcover = self.prefs.get('Cover_wanted', False)
        return wcover

    @property
    def with_pretty_comments(self):
        x = getattr(self, 'wpcomment', None)
        if x is not None:
            return x
        wpcomment = self.prefs.get('Pretty_wanted', False)
        return wpcomment

    @property
    def with_detailed_rating(self):
        x = getattr(self, 'wrcomment', None)
        if x is not None:
            return x
        wrcomment = self.prefs.get('Detailled_Rating_wanted', False)
        return wrcomment

    @property
    def tag_genre(self):
        x = getattr(self, 'wgtag', None)
        if x is not None:
            return x
        wgtag = self.prefs.get('tag_genre_combien', False)
        return wgtag

    @property
    def tag_theme(self):
        x = getattr(self, 'wttag', None)
        if x is not None:
            return x
        wttag = self.prefs.get('tag_theme_combien', False)
        return wttag

    @property
    def tag_lieu(self):
        x = getattr(self, 'wltag', None)
        if x is not None:
            return x
        wltag = self.prefs.get('tag_lieu_combien', False)
        return wltag

    @property
    def tag_quand(self):
        x = getattr(self, 'wqtag', None)
        if x is not None:
            return x
        wqtag = self.prefs.get('tag_quand_combien', False)
        return wqtag

    def get_book_url(self, identifiers):
        '''
        get_book_url : used by calibre to convert the identifier to an URL...
        return an url if bbl_id exists and is valid.
        For this to work, we need to define or find the minimum info to build a relevant url.
        '''
        # For babelio, this seems to be: URL_BASE+"nom-de-l-auteur-le-titre-du-livre/<une serie de chiffres>"
        # that is: BASE_URL + "/livres/" + bbl_id or just: https://www.babelio.com/livres/ + bbl_id
        # example over an url :
        # https://www.babelio.com/livres/Savater-Il-giardino-dei-dubbi-Lettere-tra-Voltaire-e-Caro/598832
        # "https://www.babelio.com/livres/"+"Savater-Il-giardino-dei-dubbi-Lettere-tra-Voltaire-e-Caro/598832"

        bbl_id = identifiers.get(Babelio.ID_NAME, None)
        if bbl_id and "/" in bbl_id and bbl_id.split("/")[-1].isnumeric():
            return (self.ID_NAME, bbl_id, "https://www.babelio.com/livres/" + bbl_id)

    def id_from_url(self, url):
        '''
        id_from_url : takes an URL and extracts the identifier details...
        Id must be unique enough for other plugin(s) to verify/adopt, or not, this id
        '''
        bbl_id = ""
        if "https://www.babelio.com/livres/" in url:
            bbl_id = url.replace("https://www.babelio.com/livres/","").strip()
        if "/" in bbl_id and bbl_id.split("/")[-1].isnumeric():
            return (self.ID_NAME, bbl_id)
        else:
            return None

    def create_query(self, log, title=None, authors=None, only_first_author=True):
        # '''
        # This returns an URL build with all the tokens made from both the title and the authors.
        # If title is None, returns None.
        # ! type(title) is str, type(authors) is list
        # '''
        '''
        This returns both an URL and a data request for a POST request to babelio.com
        This is a change from previous babelio_db that used to need a GET request
        If title is None, returns None.
        ! type(title) is str, type(authors) is list
        '''
        debug=self.dbg_lvl & 1
        if debug:
            log.info('in create_query()\n')
            log.info('title       : ', title)
            log.info('authors     : ', authors)

        # BASE_URL_FIRST = 'http://www.babelio.com/resrecherche.php?Recherche='
        # BASE_URL_LAST = "&amp;tri=auteur&amp;item_recherche=livres&amp;pageN=1"
        ti = ''
        au = ''
        url = "https://www.babelio.com/recherche"
        rkt = None

        if authors:
            for i in range(len(authors)):
                authors[i] = ret_clean_text(log, self.dbg_lvl, authors[i])
            author_tokens = self.get_author_tokens(authors, only_first_author=only_first_author)
        #     au='+'.join(author_tokens)
            au=' '.join(author_tokens)

        title = ret_clean_text(log, self.dbg_lvl, title)
        title_tokens = list(self.get_title_tokens(title, strip_joiners=False, strip_subtitle=True))
        # ti='+'.join(title_tokens)
        ti=' '.join(title_tokens)

        # query = BASE_URL_FIRST+('+'.join((au,ti)).strip('+'))+BASE_URL_LAST
        # if debug: log.info("return query from create_query : ", query)
        # return query
        rkt = {"Recherche":(' '.join((au,ti))).strip()}
        if debug:
            log.info("return url from create_query : ", url)
            log.info("return rkt from create_query : ", rkt)
        return url, rkt

    def identify(self, log, result_queue, abort, title=None, authors=None, identifiers={}, timeout=30):
        '''
        this is the entry point...
        Note this method will retry without identifiers automatically... read can be resubmitted from inside it
        if no match is found with identifiers.
        '''
        log.info('-+-+-+-+-+-+-+-+-+-+ Entry point +-+-+-+-+-+-+-+-+-+-')

      # The kludge...               #
      # the lockfile exists, so we do NOT access babelio for LOCK_TIME
        if os.path.exists(os.path.join(tempfile.gettempdir(),"Babelio_dbpleaseabortworker.tmp")):
            log.info('Babelio_dbpleaseabortworker.tmp existe, on ne va pas plus loin...')                   # Babelio_dbpleaseabortworker.tmp exists, abort
            fl_rsbl = (datetime.datetime.now() + LOCK_TIME).strftime('%d-%m-%Y à %H:%M:%S')                 # calculate when file can be deleted
            log.info(f"redemarez calibre au plus tôt le {fl_rsbl}")                                         # tell when lockfile is erable
            log.info('Grâce à ça, on évite de corrompre les données de calibre (ce qui est bon), et, ')     # BUT this avoid calibre corruption (that is good)')
            log.info('AUSSI, on évite de noyer Babelio avec des requêtes inutiles (ce qui est très bon).')  # AND avoid swamping Babelio with useless request (that is very good)')
            log.info("Kludge, peut-être, mais c'est vraiment le mieux que j'ai trouvé.\n")                  # Kludge, maybe, but this is the best I could think off')
            return

        log.info('self.dgb_lvl              : ', self.dbg_lvl)
        log.info('self.with_cover           : ', self.with_cover)
        log.info('self.with_pretty_comments : ', self.with_pretty_comments)
        log.info('self.with_detailed_rating : ', self.with_detailed_rating)
        log.info('self.tag_genre            : ', self.tag_genre)
        log.info('self.tag_theme            : ', self.tag_theme)
        log.info('self.tag_lieu             : ', self.tag_lieu)
        log.info('self.tag_quand            : ', self.tag_quand)
        log.info('\nIn identify(self, log, result_queue, abort, title=.., authors=.., identifiers=.., timeout=30)\n')

        debug=self.dbg_lvl & 1
        debugt=self.dbg_lvl & 8
        if debug:
            log.info("title             : ", title)
            log.info("identifiers       : ", identifiers)
            log.info("authors           : ", authors, type(authors))

        nknwn = ['Inconnu(e)', 'Unknown','Inconnu','Sconosciuto','Necunoscut(ă)']   #français, anglais, français(Canada), italien, roman
        for i in range(len(nknwn)):
            if authors and nknwn[i] in authors[0]:
                authors = None
                if debug: log.info("authors Unknown processed : ", authors)
                break

        query, rkt = None, None
        matches = []
        br = self.browser

      # on a des identifiers
        if identifiers:
          # En premier, on essaye de charger la page si un id babelio existe
            tmp_matches = self.get_book_url(identifiers)
            old_id = identifiers.get('babelio', None)
            if old_id and "/" in old_id and old_id.split("/")[-1].isnumeric():
                tmp_matches = (self.ID_NAME, old_id, "https://www.babelio.com/livres/" + old_id)
            if tmp_matches:
                matches = [tmp_matches[2]]
                log.info("babelio identifier trouvé... pas de recherche sur babelio... on saute directement au livre\n")

          # ensuite, on essaye de charger la page si un ISBN existe
          # attention babelio changed from get to post: Body: Key : "Recherche" Value : "ken follett un monde sans fin"
          # attention url "https://www.babelio.com/recherche"
          # def verify_isbn(log, dbg_lvl, isbn_str, who=''):
            if not matches:
                isbn = check_isbn(identifiers.get('isbn', None))
                if isbn:
                    query= "https://www.babelio.com/recherche"
                    rkt = {"Recherche":isbn}
                    log.info("ISBN identifier trouvé, on cherche cet ISBN sur babelio : ", query)
                    soup=ret_soup(log, self.dbg_lvl, br, query, rkt=rkt)[0]
                    matches = self.parse_search_results(log, title, authors, soup, br)
                    query=None

      # Enfin sauf identifiers, on essaye auteur+titre ou même titre
      # mais titre doit exister (create_query return None if no title...)
        if not (title or matches):
            log.error('Métadonnées incorrectes ou insuffisantes pour la requête.')
            log.error("Verifier la validité des ids soumis (ISBN, babelio), ")
            log.error("la présence d'un titre et la bonne orthographe des auteurs.")
            return

        if not (matches or query) and authors:
            log.info("Pas de résultat avec babelio_id ou avec l'ISBN, on recherche les auteurs et le titre.\n")
            query, rkt = self.create_query(log, title=title, authors=authors, only_first_author=False)
            soup=ret_soup(log, self.dbg_lvl, br, query, rkt=rkt)[0]
            matches = self.parse_search_results(log, title, authors, soup, br)
            query=None

      # tous les auteurs ensemble ne donnent pas de résultats, on tente avec le titre et un auteur individuellement
        if not (matches or query) and authors and len(authors) > 1 :
            log.info("Pas de résultat avec tous les auteurs, on n'en n'utilise qu'un.", end=" ")
            for n in range(len(authors)):
                log.info('Auteur utilisé : ', authors[n],'\n')
                query, rkt = self.create_query(log, title=title, authors=[authors[n]])
                soup=ret_soup(log, self.dbg_lvl, br, query, rkt=rkt)[0]
                matches = self.parse_search_results(log, title, authors, soup, br)
                query=None
                if matches: break

      # ok seul le titre peut encore apporter un résultat...
        if not (matches or query):
            log.info('Pas de résultat, on utilise uniquement le titre (on peut avoir de la chance! ).\n')
            query, rkt = self.create_query(log, title=title)
            soup=ret_soup(log, self.dbg_lvl, br, query, rkt=rkt)[0]
            matches = self.parse_search_results(log, title, authors, soup, br)
            if not matches:
                log.error('Pas de résultat pour la requête : ', query)
                log.error("Soit ce livre n'est pas connu de babelio, soit les métadonnées ")
                log.error('sont incorrectes ou insuffisantes pour la requête.')
                log.error("Verifier la présence d'un titre, la bonne orthographe des auteurs")
                log.error("et la validité des ids soumis (ISBN, babelio).")
                return

        if debug: log.info("matches : ", matches)

        if abort.is_set():
            if debug:
                log.info("abort is set...")
            return

        from calibre_plugins.babelio_db.worker import Worker
        workers = [Worker(url, result_queue, br, log, i, self, self.dbg_lvl) for i, url in enumerate(matches)]

        for w in workers:
            if debug: log.info("submit time                : ", time.asctime())
            w.start()
            # time.sleep(1)           # Don't send all requests at the same time, make sure only one request per second

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

        if debugt:
            log.info("\ntiming of the accesses to Babelio for this book")
            for i in (ret_soup.get_memory()):
                log.info("When : {}; Who : {}; Where : {}".format(i[1],i[2],i[0]))

        return None                 # job done

    def parse_search_results(self, log, orig_title, orig_authors, soup, br):
        '''
        this method returns "matches".
        note: if several matches, the first presented in babelio will be the first in the
        matches list; it will be submited as the first worker... (highest priority)
        Note: only the first Babelio page will be taken into account (10 books maximum)
        '''
        log.info('In parse_search_results(self, log, orig_title, orig_authors, soup, br)')
        debug=self.dbg_lvl & 1
        if debug:
            log.info("orig_title    : ", orig_title)
            log.info("orig_authors  : ", orig_authors)

        unsrt_match, matches = [], []
        lwr_serie = ""
        x=None
      # only use the first page found by babelio.com, that is a maximum of 10 books
      # first lets get possible serie name in lower string (we do not want lose a possible ":")
        x = soup.select_one(".resultats_haut")
        if x:
            # if debug: log.info('display serie found\n',x.prettify())                        # hide it
            lwr_serie = x.text.strip().lower()
            # if debug: log.info(f"lwr_serie, that is x.text.strip().lower() : {lwr_serie}")                     # hide it

        x = soup.select(".cr_meta")
        if len(x):
            for i in range(len(x)):
                # if debug: log.info('display each item found\n',x[i].prettify())             # hide it

                titre = (x[i].select_one(".titre1")).text.strip()
              # first delete serie info in titre if present
                if lwr_serie:
                  # get rid of serie name (assume serie name in first position with last char always "," and first ":" isolate title for serial name)
                  # then split on first occurence of ":" and get second part of the string, that is the title
                    titre = titre.lower().replace(lwr_serie+",","").split(":",1)[1]
                    log.info(f"titre.lower().replace(lwr_serie+',','') ; {titre}")

                ttl = ret_clean_text(log, self.dbg_lvl, titre)
                orig_ttl = ret_clean_text(log, self.dbg_lvl, orig_title)
                sous_url = (x[i].select_one(".titre1"))["href"].strip()
                auteur = (x[i].select_one(".libelle")).text.strip()
                aut = ret_clean_text(log, self.dbg_lvl, auteur)

                max_Ratio = 0
                if orig_authors:
                    for i in range(len(orig_authors)):
                        orig_authors[i] = ret_clean_text(log, self.dbg_lvl, orig_authors[i])
                        aut_ratio = SM(None,aut,orig_authors[i]).ratio()        # compute ratio comparing auteur presented by babelio to each item of requested authors
                        if aut_ratio < 0.6 : aut_ratio = 0                      # diregard if not similar
                        max_Ratio = max(max_Ratio, aut_ratio)                   # compute and find max ratio comparing auteur presented by babelio to each item of requested authors

                ttl_ratio = SM(None,ttl, orig_ttl).ratio()                      # compute ratio comparing titre presented by babelio to requested title
                if ttl_ratio < 0.6 : ttl_ratio = 0                              # diregard if not similar
                if ttl_ratio + max_Ratio:                                       # if at least either title or author is similar (idealy should be 2)
                    unsrt_match.append((sous_url, ttl_ratio + max_Ratio))       # take it as a match

                if debug: log.info(f'titre, ratio : {titre}, {ttl_ratio},    auteur, ratio : {auteur}, {max_Ratio},  sous_url : {sous_url}')

        srt_match = sorted(unsrt_match, key= lambda x: x[1], reverse=True)      # find best matches over the orig_title and orig_authors

        log.info('nombre de références trouvées dans babelio', len(srt_match))
        # if debug:                                                                           # hide_it # may be long
        #     for i in range(len(srt_match)): log.info('srt_match[i] : ', srt_match[i])       # hide_it # may be long

        for i in range(len(srt_match)):
            matches.append(Babelio.BASE_URL + srt_match[i][0])
          # if ratio = 2 (exact match on both author and title) then present only this book for this author
            if srt_match[i][1] == 2:
                log.info("YES, perfect match on both author and title, take only one.")
                break

        if not matches:
            if debug:
                log.info("matches at return time : ", len(matches))
            return None
        else:
            log.info("nombre de matches : ", len(matches))
            if debug:
                log.info("matches at return time : ")
                for i in range(len(matches)):
                    log.info("     ", matches[i])

        return matches

    def get_cached_cover_url(self, identifiers):
        '''
        retrieve url address of the cover associated with NAME_id or ISBN
        '''
        if not self.with_cover:
            return None
        url = None
        bbl_id = identifiers.get(Babelio.ID_NAME, None)
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
# that is working during development but it is NOT a quality test as the site
# has NO waranted stability... this is left just for example of the structure

if __name__ == '__main__':

  # Run these tests from the directory containing all files needed for the plugin (the files that go into the zip file)
  # that is: __init__.py, plugin-import-name-babelio_db.txt and optional .py such as worker.py, ui.py, whatever...
  # from a terminal issue in sequence:
  # calibre-customize -b .
  # calibre-debug -e __init__.py
  # attention: on peut voir un message prévenant d'une erreur... en fait ce message est activé par la longueur du log... (parfois fort grand)
  # Careful, a message may pop up about an error... however this message pops up function of the length of the log... (sometime quite big)
  # anyway, verify... I have been caught at least once

    from calibre.ebooks.metadata.sources.test import (test_identify_plugin, title_test, authors_test, series_test)
    test_identify_plugin(Babelio.name,
        [
            # ( # A book with ISBN specified, ISBN not found in babelio so using title+authors
            #     {'identifiers':{'isbn': '9781846148200'}, 'title':"Il est avantageux d'avoir où aller", 'authors':['Emmanuel Carrère']},
            #     [title_test("Il est avantageux d'avoir où aller", exact=False), authors_test(['Emmanuel Carrère'])]
            # ),

            ( # A book with ISBN specified, as series is none, series_test will fail
                {'identifiers':{'isbn': '97820704485'}, 'title':'Le chasseur et son ombre', 'authors':['George R. R. Martin','Daniel Abraham','Gardner Dozois']},
                [title_test("Le chasseur et son ombre", exact=True), authors_test(['George R. R. Martin','Daniel Abraham','Gardner Dozois'])]
            )
        ]
        )
