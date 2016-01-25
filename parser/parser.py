# coding=utf-8
from pprint import pprint

__author__ = 'gregoryvit'

from lxml import html
import requests
import re
import freecite
import json
import urllib


def map_references(references):
    if references:
        client = freecite.Client()
        results = [result for result in client.parse_many(references)]
        return results
    return


def string_without_last_dot(string):
    if len(string) > 0 and string[-1] == '.':
        return string[:-1]
    return string


def map_pages_string(pages_string):
    results = re.findall('\d+', pages_string)
    if results > 1:
        return {'from': results[0], 'to': results[1]}
    return pages_string


def map_date_string(date_string):
    results = re.findall('\d+', date_string)
    if results > 2:
        return results
    return date_string


def clean_name_string(string):
    stripped_string = string.strip()

    first_character_index = 0
    for i, c in enumerate(stripped_string):
        if c.isupper():
            first_character_index = i
            break
    return stripped_string[first_character_index:]


def url_to_path(url):
    return '/' + '/'.join(url.replace('http://www.', 'http://').replace('http://', '').split('/')[1:]).strip()


def num(s):
    try:
        return int(s)
    except ValueError:
        return


def number_from_string(s):
    import re
    results = re.findall('\d+', s)
    if results:
        return num(results[0])


def load_magazines(path, base_url):
    page = requests.get(base_url + path)
    tree = html.fromstring(page.content)

    titles = tree.xpath("//td[@class='news']/h3[.]/text()")

    years = [num(title) for title in titles if num(title)]

    volumes = []

    cnt = 1
    while True:
        current_volumes = tree.xpath("//td[@class='news']/h3[%d]//a[.]" % cnt)
        cnt += 1

        if current_volumes:
            volumes.append(current_volumes)

        if cnt > 20:
            break

    results = {
        years[i]: [{
                       "number": number_from_string(cur.text),
                       "path": url_to_path(cur.attrib['href'])
                   } for cur in volume if number_from_string(cur.text)]
        for i, volume in enumerate(volumes)
        }

    return results


def load_magazine_publications(path, base_url):
    page = requests.get(base_url + path)
    tree = html.fromstring(page.content)

    # titles = tree.xpath("//p[@class='MsoNormal'][.] | //p[@class='TOCTitle'][.]")
    titles = tree.xpath("//td[@class='news']//p[.]")

    results = []

    current_titles = []

    def is_pages_title(title):
        # print title
        pages_results = re.findall(r"^.{,10}\d+[-]+\d+", title, flags=re.MULTILINE)
        if pages_results:
            # print title
            return True

    all_titles = []

    for title in titles:
        for br in title.xpath("*//br"):
            br.tail = "\n" + br.tail if br.tail else "\n"

        text = title.text_content()

        current_lines = [line.strip() for line in text.split('\n')]

        current_text_titles = [
            {
                'text': line,
                'element': title
            }
            for line in current_lines
            ]

        all_titles.extend(current_text_titles)

    for title_dict in all_titles:
        text = title_dict['text']

        if not text:
            continue

        is_uppercase_letter = reduce(lambda a, b: a and b, map(lambda l: l.isupper() or not l.isalpha(), text))

        if is_uppercase_letter:
            continue

        link_elements = title_dict['element'].xpath(".//a[.]")
        links = [link_element.attrib['href'] for link_element in link_elements if 'href' in link_element.attrib]

        current_titles.append(text)

        if not is_pages_title(text):
            continue

        if len(current_titles) < 3:
            continue

        current_publication = {}

        article_urls = [link for link in links if '.pdf' in link]
        if article_urls:
            current_publication['article_url'] = article_urls[0].strip()

        annotation_urls = [link for link in links if '.html' in link]
        if annotation_urls:
            current_publication['annotation_path'] = url_to_path(annotation_urls[0])

        pages_value = ''
        pages = re.findall('\d+[^\d]\d+', current_titles.pop())
        if pages:
            pages_value = pages[0]

        current_publication['pages'] = map_pages_string(pages_value)
        current_publication['authors'] = [author.strip() for author in current_titles.pop().split(',')]
        current_publication['title'] = '\n'.join(current_titles)

        results.append(current_publication)
        current_titles = []

    # print results

    for publication in results:
        if 'annotation_path' in publication:
            publication.update(load_publication_info(publication['annotation_path'], base_url))

    return results


def load_publication_info(path, base_url):
    page = requests.get(base_url + path)
    tree = html.fromstring(page.content)

    # print base_url + path

    annotation_elements = tree.xpath("//td[@class='news']")

    if annotation_elements:
        element = annotation_elements[0]
        for br in element.xpath("*//br"):
            br.tail = "\n" + br.tail if br.tail else "\n"
        result = element.text_content()
        result = re.sub('^[\s ]*\n+', '\n', result, flags=re.MULTILINE)
        result_lines = result.split('\n')

        publication_info = {}

        references = []
        other_lines = []

        # print path

        current_line_type = 'authors'
        for current_line in result_lines:
            current_line = current_line.strip()

            if current_line == u'' and current_line_type != 'authors':
                current_line_type = ''
            elif current_line != u'' and current_line_type == 'authors':
                authors = map(clean_name_string, current_line.split(';'))

                authors_data = [
                    {
                        'name': author_string.split(',')[0].replace('*', ''),
                        'grade': author_string.split(',')[1].strip()
                    }
                    for author_string in authors if len(author_string.split(',')) >= 2
                    ]

                publication_info['authors'] = authors_data

                current_line_type = ''
            elif current_line_type == 'references':
                reference_string = re.findall('^\d+\.(.*)', current_line, flags=re.MULTILINE)
                if reference_string:
                    references.append(reference_string[0].strip())
            elif u'литература' in current_line.lower() or 'references' in current_line.lower():
                current_line_type = 'references'
            elif u'OCIS' in current_line or u'ОСIS' in current_line or u'OGIS' in current_line or u'OSIC' in current_line or u'OCiS' in current_line:
                ocis_codes_string = current_line.split(':')
                if len(ocis_codes_string) > 1:
                    publication_info['ocis_codes'] = map(string_without_last_dot,
                                                         map(unicode.strip, ocis_codes_string[1].split(', ')))
            elif u'УДК' in current_line or u'УКД' in current_line or 'UDC' in current_line or 'UDK' in current_line:
                udc_codes_string = current_line.split(':')
                if len(udc_codes_string) > 1:
                    publication_info['udc_codes'] = map(string_without_last_dot,
                                                        map(unicode.strip, udc_codes_string[1].split(',')))
            elif u'ключевые слова:' in current_line.lower() or 'keyword:' in current_line.lower() or 'keywords:' in current_line.lower() or 'key words:' in current_line.lower() or u'ключевые  слова:' in current_line.lower():
                keywords_codes_string = current_line.split(':')
                if len(keywords_codes_string) > 1:
                    publication_info['keywords_codes'] = map(string_without_last_dot,
                                                             map(unicode.strip, keywords_codes_string[1].split(', ')))
            elif u'поступила в редакцию' in current_line.lower() or 'Submitted' in current_line or 'Received' in current_line or u'Поступила ' in current_line:
                result_received_date = re.findall('\d+.\d+.\d+', current_line)
                if result_received_date:
                    publication_info['received_date'] = map_date_string(result_received_date[0])
            else:
                other_lines.append(current_line)

        if references:
            publication_info['references'] = map_references(references)

        if other_lines:
            max_line = ''
            for line in other_lines:
                if len(max_line) < len(line):
                    max_line = line
            if len(max_line) > 0:
                publication_info['description'] = max_line

        return publication_info

    return {}


def load_data():
    base_url = 'http://opticjourn.ru'

    magazines = load_magazines('/emags.html', base_url)

    loaded_data = {
        year: [{
                   'number': volume['number'],
                   'path': volume['path'],
                   'articles': load_magazine_publications(volume['path'], base_url)
               } for volume in volumes]
        for year, volumes in magazines.iteritems()
        }

    with open('results.json', 'w+') as the_file:
        the_file.write(json.dumps(loaded_data))


from rdflib import Graph, URIRef, BNode, Literal, Namespace
from rdflib.namespace import RDF, FOAF, XSD


def rdf_resource(resource_name):
    n = Namespace("http://example.org/people/")

    map_dict = [
        ['Article', 'RCVKz6OEi5rIcicOxquej0D'],
        ['Author', 'RCsynwco1lNUQSsvKWT1R0B'],
        ['Degree', 'RBHBiJft0rtFffF2YgVz4Cm'],
        ['Volume', 'RBsLWiCOTvVBkqJ7ydEOUzZ'],
        ['description', 'RDhDg1ElS8IcTFRLUn3TG8'],
        ['title', 'RYy1OIRPJQplAn7FJC9xHp'],
        ['article_url', 'RDFPrhX68pZsRQ5NHuRMQe7'],
        ['ocis_codes', 'RoNPbI6VM2sfQeQMAiCP7i'],
        ['udc_codes', 'R9IM7u2M9PRflXGo8M0jkY'],
        ['keywords_codes', 'R9m0ne3covxvSEynK5zslb9'],
        ['from_page', 'RBBOGI2fxoMGuPFz2JThOOl'],
        ['to_page', 'R8tfbXbtSOEEgaBsrgi1pAc'],
        ['received_date', 'R718g5LMORvxE9oaN1Fr1et'],
        ['references', 'RBYnSi3XtGUdI7mbLYX9WGE'],
        ['name', 'RBOssYsXvkXlxLKJ8qTxu53'],
        ['grade', 'RCHcO72LEkIK8UDU56JW3qG'],
        ['authors', 'R7T9j3EvmeuTp9LIZ35kg1Y'],
        ['articles', 'RiTFyuRnnCmZwDHFwVbEX5'],
        ['number', 'R9d8CeyfbC5EL6ResACOLsQ'],
        ['year', 'R92IguB49CXQNGjTzS628A3']
    ]

    for element in map_dict:
        if resource_name == element[0]:
            return n[element[1]]

    return None


def rdf_from_degree(degree, graph):
    degree_res = BNode()
    graph.add((degree_res, RDF.type, rdf_resource('Degree')))
    graph.add((degree_res, rdf_resource('name'), Literal(degree)))

    return degree_res


def rdf_from_author(author, graph):
    author_res = BNode()
    graph.add((author_res, RDF.type, rdf_resource('Author')))

    if 'name' in author:
        graph.add((author_res, rdf_resource('name'), Literal(author['name'])))

    if 'grade' in author:
        graph.add((author_res, rdf_resource('grade'), rdf_from_degree(author['grade'], graph)))

    return author_res


def rdf_from_article(article, graph):
    if 'annotation_path' not in article:
        return

    article_res = URIRef('http://' + urllib.quote('opticjourn.ru' + article['annotation_path']))
    graph.add((article_res, RDF.type, rdf_resource('Article')))

    for key, value in article.iteritems():
        if isinstance(value, unicode):
            if key != 'annotation_path' and key != 'article_url':
                graph.add((article_res, rdf_resource(key), Literal(value)))
            elif key == 'article_url':
                graph.add(
                    (article_res, rdf_resource(key), URIRef('http://' + urllib.quote(value.replace('http://', '')))))
        if isinstance(value, list):
            if key in ['ocis_codes', 'keywords_codes', 'udc_codes']:
                for list_value in value:
                    graph.add((article_res, rdf_resource(key), Literal(list_value)))
            elif key == 'received_date':
                graph.add((article_res, rdf_resource(key), Literal('-'.join(reversed(value)), datatype=XSD.date)))
            elif key == 'references':
                for reference in value:
                    graph.add((article_res, rdf_resource(key), Literal(reference['raw_string'])))
            elif key == 'authors':
                for author in value:
                    graph.add((article_res, rdf_resource(key), rdf_from_author(author, graph)))
        if key == 'pages':
            graph.add((article_res, rdf_resource('from_page'), Literal(value['from'])))
            graph.add((article_res, rdf_resource('to_page'), Literal(value['to'])))

    return article_res


def rdf_from_volume(volume, year, graph):
    volume_res = URIRef('http://' + urllib.quote('opticjourn.ru' + volume['path']))
    graph.add((volume_res, RDF.type, rdf_resource('Volume')))

    if 'number' in volume:
        graph.add((volume_res, rdf_resource('number'), Literal(volume['number'])))

    for article in volume['articles']:
        article_res = rdf_from_article(article, graph)
        if article_res:
            graph.add((volume_res, rdf_resource('articles'), article_res))

    graph.add((volume_res, rdf_resource('year'), Literal(year, datatype=XSD.date)))

    return volume_res


def make_rdf():
    with open('results.json', 'r') as the_file:
        data = json.loads(the_file.read())

        graph = Graph()

        for year, volumes in data.iteritems():
            for volume in volumes:
                rdf_from_volume(volume, year, graph)

        print graph.serialize(destination='result.ttl', format='turtle')


make_rdf()
