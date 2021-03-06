from collections import OrderedDict

from datetime import datetime
import lxml.html
import requests
import scraperwiki

normattiva_url = "http://www.normattiva.it"


def _get_relative_url(absolute_url, base_url=normattiva_url):
    """elimina la base_url da una url assoluta

    :param absolute_url:
    :param base_url:
    :return: string
    """
    return absolute_url.replace(base_url, '')


def _get_absolute_url(relative_url, base_url=normattiva_url):
    """torna una url assoluta, partendo da una relativa

    :param relative_url:
    :param base_url:
    :return: string
    """
    return "{0}{1}".format(base_url, relative_url)


def _get_permalinks(tmp_url, session=None):
    """

    :param tmp_url:
    :param session:
    :return: lista di permalink
    """
    norma_url_tmp = _get_absolute_url(tmp_url)
    norma_res_tmp = session.get(norma_url_tmp)

    if norma_res_tmp.status_code == 404:
        return None

    norma_el_tmp = lxml.html.fromstring(norma_res_tmp.content)

    permalinks = []
    risultati_href = set([
        link.attrib['href'] for link in
        norma_el_tmp.cssselect("#corpo_risultati a")
    ])
    if risultati_href:
        for risultato_href in risultati_href:
            permalinks.append(
                _get_permalink(
                    _get_absolute_url(risultato_href),
                    session
                )
            )
    else:
        permalinks.append(
            _get_permalink(
                norma_url_tmp,
                session
            )
        )

    return filter(lambda x: x is not None, permalinks)


def _get_permalink(tmp_url, session=None):
    """torna un permalink con la urn completa,
    partendo da una url con urn parziale

    :param tmp_url:
    :param session: la sessione di navigazione in normattiva
    :return: stringa o None
    """
    if session is None:
        print("La sessione deve essere specificata")
        return None

    # si determina il permalink, con la URN permanente
    norma_res_tmp = session.get(tmp_url)
    norma_el_tmp = lxml.html.fromstring(norma_res_tmp.content)
    if 'Provvedimento non trovato in banca dati' in norma_res_tmp.content:
        return None
    permalink_href = norma_el_tmp.cssselect(
        "img[alt='Collegamento permanente']"
    )[0].getparent().attrib['href']
    permalink_url = _get_absolute_url(permalink_href)
    permalink_res = session.get(permalink_url)
    permalink_el = lxml.html.fromstring(permalink_res.content)
    norma_urn_href = permalink_el.cssselect(
        '#corpo_errore a'
    )[0].attrib['href']
    return norma_urn_href


def _get_name_type_year(norma_urn):
    """Extract name, type and year from a urn.
    Return None in case of parser error

    :param norma_urn: the urn, containing the number
    :return: tuple with name and type or None
    """
    norma_inner_urn, norma_number = norma_urn.split(';')
    norma_dotted_type = norma_inner_urn.split(':')[3]
    norma_type = ' '.join(
        map(
            lambda x: x.title(),
            norma_dotted_type.split('.')
        )
    )
    norma_type_initials = ''.join(
        map(lambda x: x[0] + ".", norma_type.split())
    )
    original_date = norma_inner_urn.split(':')[4]
    norma_date = norma_year = None
    try:
        norma_date = datetime.strptime(
            original_date, '%Y-%m-%d'
        ).strftime('%d/%m/%Y')
        norma_year = datetime.strptime(
            original_date, '%Y-%m-%d'
        ).strftime('%Y')
    except ValueError:
        try:
            norma_date = datetime.strptime(
                original_date, '%Y'
            ).strftime('%Y')
            norma_year = norma_date
        except ValueError as e:
            if 'unconverted data remains' in e.args[0]:
                unconverted_data = e.args[0].split(':')[1].strip()
                norma_date = original_date.replace(unconverted_data, '')
                try:
                    norma_date = datetime.strptime(norma_date, '%Y').strftime('%Y')
                    norma_year = norma_date
                except ValueError:
                    return (None, None, None)

    norma_name = "{0} {1} del {2}".format(
        norma_type_initials, norma_number,
        norma_date
    )

    return (norma_name, norma_type, norma_year)


def process_permalinks(permalinks, session=None):
    """Processa una lista di permalink

    :param permalinks: lista di url da parsare (relative)
    :param session: Sessione di navigazione in normattiva
    :return: -
    """

    if session is None:
        print("La sessione deve essere specificata")
        return None

    for permalink_url in permalinks:
        # read norma dal permalink
        norma_url = _get_absolute_url(permalink_url)
        norma_urn = permalink_url.split('?')[1].split('!')[0]

        print(permalink_url)

        if 'urn' not in norma_urn:
            continue

        norma_res = session.get(norma_url)
        norma_el = lxml.html.fromstring(norma_res.content)

        norma_name, norma_type, norma_year = _get_name_type_year(norma_urn)
        if norma_name is None:
            continue

        titolo = ''
        title = ''
        description = ''

        testa = norma_el.cssselect('#testa_atto p')
        if testa:
            titolo = testa[0].text
            title = ' '.join(
                titolo.strip().split()
            )

        testa = norma_el.cssselect('#testa_atto')
        if testa:
            description = ' '.join(
                testa[0].text_content().\
                    replace(titolo, '').strip().split()
            )

        data = {
            'Type': norma_type,
            'Name': norma_name,
            'Title': title,
            'Description': description,
            'Image': '',
            'Reference': norma_url,
            'URN': norma_urn,
            'Year': norma_year,
            'Scraped': 1
        }
        scraperwiki.sql.save(
            ['Type', 'Name'],
            data=data,
            table_name='Nodes'
        )

        # estrae la toc, dall'iframe
        toc_src = norma_el.cssselect("#leftFrame")[0].attrib['src']
        toc_url = _get_absolute_url(toc_src)
        toc_res = session.get(toc_url)
        toc_el = lxml.html.fromstring(toc_res.content)

        # loop sugli articoli
        # e aggiungi links trovati al set
        links = set()
        for a in toc_el.cssselect("#albero li a"):
            art_src = a.attrib['href'].replace(
                'atto/caricaArticolo',
                'do/atto/caricaRiferimentiURN'
            )
            art_url = _get_absolute_url(art_src)

            # leggi contenuto articolo
            art_res = session.get(art_url)
            art_el = lxml.html.fromstring(art_res.content)

            # estrai link e aggiungili (unione)
            # al set di tutti i link
            links |= set([
                l.attrib['href'].split('~')[0]
                for l in art_el.cssselect(
                    "#dx_dettaglio div.wrapper_pre pre a"
                ) if 'urn' in l.attrib['href'] and ';' in l.attrib['href']

            ])

        # metti i dati nelle tabelle,
        # compatibili con GraphCommons
        nodes_data = []
        edges_data = []
        for l in links:
            l_url = _get_absolute_url(l)
            l_urn = l.split('?')[1].split('!')[0]
            name, type, year = _get_name_type_year(l_urn)
            if name is None:
                continue

            node_exists = scraperwiki.sql.select(
                "count(*) as n from Nodes where URN='%s'" % l_urn
            )[0]['n']
            if node_exists == 0:
                nodes_data.append({
                    'Type': type,
                    'Name': name,
                    'Title': '',
                    'Description': '',
                    'Image': '',
                    'Reference': l_url,
                    'URN': l_urn,
                    'Year': year,
                    'Scraped': 0,
                })
            edges_data.append({
                'From Type': norma_type,
                'From Name': norma_name,
                'Edge': 'REFERS_TO',
                'To Type': type,
                'To Name': name
            })
        scraperwiki.sql.save(
            ['Type', 'Name'],
            data=nodes_data,
            table_name='Nodes'
        )
        scraperwiki.sql.save(
            ['From Type', 'From Name', 'Edge',
             'To Type', 'To Name' ],
            data=edges_data,
            table_name='Edges'
        )


if __name__ == '__main__':

    norme_anno = OrderedDict([
        # (2016, 249),
        # (2015, 222),
        # (2014, 203),
        # (2013, 159),
        # (2012, 263),
        # (2011, 237),
        # (2010, 277),
        # (2009, 220),
        # (2008, 222),
        # (2007, 278),
    ])

    # genera istanza di navigazione,
    # con header modificati
    with requests.session() as session:
        session.headers.update({
            'User-agent': "Mozilla/5.0"
                "(Macintosh; Intel Mac OS X 10_11_6) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/55.0.2883.95 Safari/537.36",
            'Connection': 'keep-alive'
        })

        for anno, n_norme in norme_anno.items():
            for k in range(1, n_norme+1):
                norma_url = "/uri-res/N2Ls?urn:nir:{0};{1}!vig=".format(
                    anno, k
                )
                print(norma_url)

                # urn e url parziali della norma
                process_permalinks(
                    _get_permalinks(
                        norma_url,
                        session=session
                    ),
                    session=session
                )
                scraperwiki.status('ok')

        # explore and solve referenced links (first passage)
        referenced_links = set([
            res['Reference'] for res in
            scraperwiki.sql.select("Reference from Nodes where Scraped = 0")
        ])
        for link in referenced_links:
            process_permalinks(
                _get_permalinks(
                    _get_relative_url(link),
                    session=session
                ),
                session=session
            )
            scraperwiki.status('ok')

