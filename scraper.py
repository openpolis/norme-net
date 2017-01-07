import lxml.html
import requests
import scraperwiki

normattiva_url = "http://www.normattiva.it"
norma_urn = "/uri-res/N2Ls?urn:nir:stato:decreto:2000-11-03;396!vig="
norma_url = "{0}{1}".format(
    normattiva_url, norma_urn
)

with requests.session() as s:
    # adjust session headers
    s.headers.update({
        'User-agent': 'Mozilla/5.0',
        'Connection': 'keep-alive'
    })

    # read norma
    norma_res = s.get(norma_url)
    norma_el = lxml.html.fromstring(norma_res.content)

    testa = norma_el.cssselect('#testa_atto p')
    titolo = testa[0].text
    title = titolo.replace('\n', '').replace('\t', '').strip()

    testa = norma_el.cssselect('#testa_atto')
    description = testa[0].text_content().\
        replace(titolo, '').replace('\n', '').replace('\t', '').\
        strip()

    data = {
        'Type': 'Norma',
        'Name': norma_urn.split('?')[1].split('!')[0],
        'Title': title,
        'Description': description,
        'Image': '',
        'Reference': norma_url
    }
    scraperwiki.sql.save(['Type', 'Name'], data=data)

    # detect and read toc iframe content
    toc_src = norma_el.cssselect("#leftFrame")[0].attrib['src']
    toc_url = "{0}{1}".format(normattiva_url, toc_src)
    toc_res = s.get(toc_url)
    toc_el = lxml.html.fromstring(toc_res.content)

    # loop over all articles
    for a in toc_el.cssselect("#albero li a"):
        art_src = a.attrib['href'].replace(
            'atto/caricaArticolo',
            'do/atto/caricaRiferimentiURN'
        )
        art_url = "{0}{1}".format(normattiva_url, art_src)

        # read article content
        print(u"parsing {0}".format(art_src))
        art_res = s.get(art_url)
        art_el = lxml.html.fromstring(art_res.content)

        # extract all links in and show first link
        links = [
            l.attrib['href']
            for l in art_el.cssselect(
                "#dx_dettaglio div.wrapper_pre pre a"
            )
        ]
        nodes_data = []
        edges_data = []
        for l in links:
            l_url = "{0}{1}".format(
                normattiva_url, l
            )
            nodes_data.append({
                'Type': 'Norma',
                'Name': l.split('?')[1].split('!')[0],
                'Title': '',
                'Description': '',
                'Image': '',
                'Reference': l_url
            })
            edges_data.append({
                'From Type': 'Norma',
                'From Name': norma_urn.split('?')[1].split('!')[0],
                'Edge': 'REFERS TO',
                'To Type': 'Norma',
                'To Name': l.split('?')[1].split('!')[0]
            })
        scraperwiki.sql.save(
            ['Type', 'Name'],
            data=nodes_data
        )
        scraperwiki.sql.save(
            ['From Type', 'From Name', 'Edge',
             'To Type', 'To Name' ],
            data=edges_data,
            table_name='Edges'
        )

