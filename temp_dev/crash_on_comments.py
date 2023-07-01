from mechanize import Browser
from bs4 import BeautifulSoup as BS
br = Browser()
url= "https://www.babelio.com/livres/Fabre-Photos-volees/615123"
import lxml

def ret_soup(br, url, rkt=None):
    '''
    Function to return the soup for beautifullsoup to work on. with:
    br is browser, url is request address, who is an aid to identify the caller,
    Un_par_un introduce a wait time to avoid DoS attack detection, rkt is the
    arguments for a     POST request, if rkt is None, the request is GET...
    return (soup, url_ret)
    '''
    debug = 1
    if debug :
        print("In ret_soup(log, dbg_lvl, br, url, rkt=none, who=''\n")
        print("br                : ", br)
        print("url               : ", url)
        print("rkt               : ", rkt)

    print("Accessing url     : ", url)

    resp = urlopen_with_retry(br, url, rkt)
    sr, url_ret = resp[0], resp[1]
    soup = BS(sr, "html5lib")

    # if debug: log.info(who,"soup.prettify() :\n",soup.prettify())               # hide_it # très utile parfois, mais que c'est long...
    return (soup, url_ret)

def urlopen_with_retry(br, url, rkt):
    '''
    this is an attempt to keep going when the connection to the site fails for no (understandable) reason
    "return (sr, sr.geturl())" with sr.geturl() the true url address of sr (the content).
    '''
    debug=1
    if debug:
        print("In urlopen_with_retry(br, url, rkt \n")

    tries, delay, backoff=4, 3, 2
    while tries > 1:
        try:
            sr = br.open(url,data=rkt,timeout=30)
            print("(urlopen_with_retry) sr.getcode()  : ", sr.getcode())
            if debug:
                print("url_vrai      : ", sr.geturl())
                print("sr.info()     : ", sr.info())
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

def parse_comments(soup):
    '''
    get resume from soup, may need access to the page again.
    Returns it with at title, html formatted.
    '''
    debug=1
    print("\n in parse_comments(self, soup)")

    comments_soup = soup.select_one('.livre_resume')
    if comments_soup.select_one('a[onclick]'):
        if debug:
            print("onclick : ",comments_soup.select_one('a[onclick]')['onclick'])
        tmp_nclck = comments_soup.select_one('a[onclick]')['onclick'].split("(")[-1].split(")")[0].split(",")
        rkt = {"type":tmp_nclck[1],"id_obj":tmp_nclck[2]}
        url = "https://www.babelio.com/aj_voir_plus_a.php"
        if debug:
            print("calling ret_soup(log, dbg_lvl, br, url, rkt=rkt, who=who")
            print("url : ",url)
            print("rkt : ",rkt)
        comments_soup = ret_soup(log, dbg_lvl, br, url, rkt=rkt, who=who)[0]

    if debug:
        print("comments prettyfied:\n", comments_soup.prettify()) # hide_it
        print("type(comments_soup) : ", type(comments_soup))
        print("comments_soup : ", comments_soup)
    return comments_soup



rsp = ret_soup(br, url)
soup = rsp[0]

# print(type(soup),len(soup))
print (soup.prettify())

comments = parse_comments(soup)

# bbl_comments = comments
"""
observe <div> is not alligned with </div>... # note, I have no idea if that is a BS bug... but to create an empty bbl_comments, then append, does work arround the problem
this produces:
comments prettyfied:
 <div class="livre_resume" id="d_bio" itemprop="description" style="margin:5px;">
 Après la perte de son emploi, Jean, un sexagénaire parisien et célibataire, se met à fréquenter le café l'Oiseau bleu. Il renoue avec quelques anciennes amies et surtout avec sa passion de jadis : la photographie. En se plongeant dans ses archives photographiques, il se remémore sa vie passée et tente de la reconstruire.
 <p class="footer" style="clear:both;border:0px;">
 </p>
</div>
"""
bbl_comments = BS('',"lxml")
bbl_comments.append(comments)
print(20*"x")
print(bbl_comments.prettify())
bbl_comments = bbl_comments.encode('ascii','xmlcharrefreplace')
