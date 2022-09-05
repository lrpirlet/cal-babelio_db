#!/usr/bin/env python3
# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai
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

class Babelio(Source):

    name = 'Babelio'
    description = 'Télécharge les métadonnées et couverture depuis Babelio.com'
    author = 'VdF'
    version = (2, 0, 0)
    minimum_calibre_version = (0, 8, 0)
    capabilities = frozenset(['identify', 'cover'])
    touched_fields = frozenset(['title', 'authors', 'identifier:isbn', 'rating', 'comments', 'publisher', 'pubdate', 'tags'])
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
            title_tokens = list(self.get_title_tokens(title,
                                strip_joiners=False, strip_subtitle=True))
            if title_tokens:
                try:
                    tokens = [quote(t.encode('iso-8859-1') if isinstance(t, str) else t) for t in title_tokens]
                    q='+'.join(tokens)
                except:
                    return None

        if authors:
            author_tokens = self.get_author_tokens(authors,
                    only_first_author=True)
            if author_tokens:
                #except UnicodeEncodError 'iso-8859-1' codec
                try:
                    tokens = [quote(t.encode('iso-8859-1') if isinstance(t, str) else t) for t in author_tokens]
                    au='+'.join(tokens)
                except:
                    return None

        if not q:
            return None

        return '%s%s%s%s%s'%(BASE_URL_FIRST,au,BASE_URL_MID,q,BASE_URL_LAST)

    print('create query')

    def identify(self, log, result_queue, abort, title=None, authors=None,
            identifiers={}, timeout=30):
        # recherche isbn https://www.babelio.com/resrecherche.php?Recherche=9782823809756&item_recherche=isbn
        matches = []
        br = self.browser
        cj = http.cookiejar.LWPCookieJar()
        br.set_cookiejar(cj)
        log.info('avant query')
        query = self.create_query(log, title=title, authors=authors, identifiers=identifiers)
        log.info('query %s' %query)
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
                log.error('Pas de résultat pour la requête : %r'.encode('latin-1') % unquote(query).encode('latin-1'))
                return
            root = fromstring(clean_ascii_chars(raw))
        except:
            msg = 'Impossible de parcourir la page babelio avec la requête : %r'.encode('latin-1') % unquote(query).encode('latin-1')
            log.exception(msg)
            return msg
        self._parse_search_results(log, title, authors, root, matches, timeout)

        if abort.is_set():
            return

        if not matches:
            if title and authors and len(authors) > 1:
                log.info('Pas de résultat avec les auteurs, on utilise uniquement le premier.'.encode('latin-1'))
                return self.identify(log, result_queue, abort, title=title,
                        authors=[authors[0]], timeout=timeout)
            elif authors and len(authors) == 1 :
                log.info('Pas de résultat, on utilise uniquement le titre.'.encode('latin-1'))
                return self.identify(log, result_queue, abort, title=title, timeout=timeout)
            log.error('Pas de résultat pour la requête : %r'.encode('latin-1') % unquote(query.encode('latin-1')))
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
        aut_res = root.xpath(".//*[@id='page_corps']/div/div[4]/div[2]/table/tbody/tr/td[3]/a")
        dict_res = dict(list(zip(titre_res, aut_res)))
        # log.info('dict', dict_res)
        if orig_aut is not None :
            ratio = 0.7
            for k in list(dict_res.keys()):
                if is_simil(orig_aut, dict_res, ratio):
                    matches.append(Babelio.BASE_URL + k.get('href'))
        else :
            for i in range(0, len(titre_res)):
                matches.append(Babelio.BASE_URL + titre_res[i].get('href'))
                matches = matches[:5]
        log.info('mat', matches)

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
            log.info('Pas de couverture trouvée.'.encode('latin-1'))
            return

        if abort.is_set():
            return
        br = self.browser

        log.info('On télécharge la couverture depuis :'.encode('latin-1'), cached_url)
        try:
            cdata = br.open_novisit(cached_url, timeout=timeout).read()
            result_queue.put((self, cdata))
        except:
            log.exception('Impossible de télécharger la couverture depuis :'.encode('latin-1'), cached_url)

