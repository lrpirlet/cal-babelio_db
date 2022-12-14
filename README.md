# Le site de Babelio

L'adresse pour accéder à Babelio est <https://www.babelio.com/>.

La page d'accueil de Babelio dit: "Babelio est un réseau social dédié aux livres et aux lecteurs. Il permet de créer et d’organiser sa bibliothèque en ligne, d’obtenir des informations sur des oeuvres, de partager et d’échanger ses goûts et impressions littéraires avec d’autres lecteurs."

Il n'est pas besoin de s'identifier pour obtenir des informations. (ce qui évite la gestion d'un acompte dans le plugin)

J'ai développé ce plugin de calibre d'après le plugin existant de VdF pour résoudre une série de limitations que je rencontre:

1. Il n'y pas de référence (id) qui permet de retrouver le URL, ni de moyen d'ajouter un id depuis le URL par manque des deux routines suivantes:
   * get_book_url : used by calibre to convert the identifier to a URL...
   * id_from_url : takes an URL and extracts the identifier details...
2. Dès que le contenu de Babelio est remonté, TOUTE l'information est traduite en utf8, TOUS les outputs (logs...) et les inputs (ce qui est lu sur le site...) sont en utf8... les multiples conversions me rendent le code confus
3. un seul matches même si deux livres répondent à la recherche
4. la compatibilité avec python 2.x me semble obsolète et perturbant.
5. Identify devrait être invoqué avec NAME_ID puis ISBN et si ça marche pas avec titre + auteur... titre seul.
6. un config.py est ok mais je préfère utiliser le config intégré, bien suffisant.
7. Babelio donne dans le titre le nom de la série et son n° de tome (ordre dans la série), je vais essayer de l'introduire (et vérifier que toutes mes séries y répondent...)
8. Je préfère nettement les commentaires en HTML et beautifulsoup (utilisé dans calibre par ailleurs)
9. J'ai horreur de ce langage de recherche et substitution (expression régulière) auquel je ne comprends pratiquement rien... enfin, un tout petit peu quoi!

Je n'ai pas retrouvé trace de VdF... Son travail , sous licence GPL V3 peut être modifié. J'aurais voulu le contacter avant de publier mon travail, basé sur le sien, sur mobileread... De toute manière, il restera visible sur github <https://github.com/lrpirlet/cal-babelio_db>

Ce travail est open source... J'ai pris du plaisir à l'écrire, si vous pensez que ce travail doit être rétribué, choisissez une association caritative et donnez leur, un peu, avec une mention comme "Thanks to Louis Richard" ou "Merci à Louis Richard" ou quelque chose de similaire dans votre langue. Cela renforcera ma réputation (non publiée)...

Quelle charité ? Mes pires cauchemars impliquent le feu, donc je donne pour les enfants profondément brûlés... Ma femme a peur du cancer donc elle donne à la recherche sur le cancer, nous nous sentons tous les deux mal à l'aise face aux gens qui meurent de faim donc nous donnons au "resto du Cœur"...

Malheureusement, il y a toujours quelqu'un qui a besoin d'aide et qui ne pourra pas rembourser (sauf peut-être avec une pensée pour l'inconnu qui l'a aidé). Il y a donc l'embarras du choix.
