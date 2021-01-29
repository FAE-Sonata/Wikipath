# -*- coding: utf-8 -*-

import numpy as np, pandas as pd
from collections import deque
import re, requests
from bs4 import BeautifulSoup
is_csv_input = False
WIKI_LEN = len("/wiki/")
while True:
    choice = input("Import search terms from a .CSV (Y/N)?: ")
    if re.match(re.compile("^([YN]|Yes|No)$", re.I), choice) != None:
        if re.match(re.compile("^Y$", re.I), choice[0]) != None:
            is_csv_input = True
        break

en_wiki_root="https://en.wikipedia.org/wiki/"
def has_article(search_term):
    if search_term.strip() == "":
        return False
    req_attempt = requests.get(en_wiki_root + search_term)
    return(req_attempt.status_code != 404)

def find_actual_title_helper(soup_from_page):
    link_titles=soup_from_page.find_all('a', title=True)
    title_text=[elem['title'] for elem in link_titles]
    has_perm=[re.search(re.compile("Permanent link"),x) != None for
             x in title_text]
    idx_perm=np.where(has_perm)
#    assert(len(idx_perm) == 1)
    if len(idx_perm[0]) != 1:
        return None
    perm_link_suffix = link_titles[idx_perm[0][0]]['href']
    char_idx_title = re.search(re.compile("title="), perm_link_suffix).end()
    char_idx_old_id = re.search(re.compile("&oldid="),
                                perm_link_suffix).start()
    return perm_link_suffix[char_idx_title:char_idx_old_id]

def find_actual_title(s):
    page = requests.get(en_wiki_root + s)
    soup_from_page = BeautifulSoup(page.text, 'html.parser')
    res = find_actual_title_helper(soup_from_page)
    if res == None:
        print("THE FOLLOWING HAD NO PERMANENT REVISION LINK:", s)
    return res
    
def links_on_page(search_term):
    page = requests.get(en_wiki_root + search_term)
    soup_from_page = BeautifulSoup(page.text, 'html.parser')
    a_tags=soup_from_page.find_all('a',href=True)
    hrefs=[elem['href'] for elem in a_tags]
    wiki_regex = re.compile("^/wiki/")
    # exclude non-mainspace article pages on Wiki, i.e. those with the
    # following prefixes:
    prefixes = ['User','Wikipedia','File','MediaWiki','Template','Help',
                'Category','Portal','Book','Draft','Education Program',
                'TimedText','Module','Gadget','Gadget definition']
    prefix_talk = [s + ' talk' for s in prefixes]
    prefixes_complete = prefixes + prefix_talk
    prefixes_complete += ['Special','Talk','MOS']
    pipe = "|"
    regexPrefixes = pipe.join(prefixes_complete)
    # also exclude the Main Page, which changes daily and will lead to
    # unstable results
    non_article_regex = re.compile("^/wiki/((" + regexPrefixes +
                                             ":)|Main_Page)", re.I)
    
    article_links = list(filter(lambda x: re.search(wiki_regex, x) != None and
                               re.search(non_article_regex, x) == None, hrefs))
    # "/wiki/" is 6 characters
    articles = [lk[WIKI_LEN:] for lk in article_links]
    unique_articles = set(articles)
    
    this_term_actual_title = find_actual_title_helper(soup_from_page)
    if this_term_actual_title in unique_articles:
        unique_articles.remove(this_term_actual_title)
    res = dict(zip(list(unique_articles), ["Linked from " + search_term
                   for s in unique_articles]))
    return res

# Reasoning adapted from Wikipedia's article on Breadth First Search
def bfs(origin_term, target_article, verbose=False):
    future_vertices = deque()
    visited = set()
    path_dict = dict()
    dist_dict = dict()
    root = origin_term
    # key stores the parent node
    path_dict[root] = None
    dist_dict[root] = 0
    current_level = -1; max_dist = 0
    future_vertices.appendleft(root)
    levels = [1E4, 5E4, 1E5, 2.5E5, 5E5, 7.5E5, 1E6, 1.5E6, 2E6, 2.5E6]
    levels.sort()
#    pd.DataFrame({'levels': levels, 'visited'})
    attained_levels = set()
#    b10K = False; b100K = False; b250K = False; b500K = False; b1M = False
    while len(future_vertices) > 0:
        subtree_root = future_vertices.pop()
        if verbose:
            num_visited = len(visited)
            num_future = len(future_vertices)
            if((num_visited > 0) and (num_visited % 1000 == 0)):
                print("==THIS ITERATION: ", str(num_visited),
                      "V; ", str(num_future),
                      "TBS; ratio of ",
                      str(float(num_future) / float(num_visited)), "==")
            if((current_level + 1) < len(levels)):
                next_level = levels[current_level + 1]
                if not(next_level in attained_levels) and len(
                        path_dict) >= next_level:
                    print("Built up", str(next_level), "entries in path",
                          "dictionary, having visited", str(len(visited)),
                          "articles with", str(len(future_vertices)),
                          "to be explored.")
                    attained_levels.add(next_level)
                    current_level += 1
       
        current_dist = dist_dict[subtree_root]
        if verbose and current_dist > max_dist:
            max_dist = current_dist
            print("Reached depth ", current_dist, " with term ", subtree_root,
                  ", having visited ", str(len(visited)), " articles and ",
                  "with ", str(len(future_vertices)), " to be explored",
                  sep="")
        if subtree_root == target_article:
            if verbose:
                print("Found path")
            return construct_path(subtree_root, path_dict)
        links = links_on_page(subtree_root)
        if target_article in set(links.keys()):
            path_dict[target_article] = subtree_root
            if verbose:
                print("1st degree connection:", target_article, "-->",
                      links[target_article])
                print("Visited", str(len(visited)), "articles;", "Added",
                      str(len(path_dict)), "entries to path dictionary")
            return construct_path(target_article, path_dict)
        link_children = set(links.keys())
        # remove articles that have been previously visited
        link_children.difference_update(visited)
        # remove articles that have already been marked for visitation
        link_children.difference_update(set(future_vertices))
        for child in link_children:
            path_dict[child] = subtree_root
            future_vertices.appendleft(child)
            dist_dict[child] = current_dist+1
        visited.add(subtree_root)

def construct_path(destination, path_dict):
    article_list = list()
    node = destination
    while path_dict[node] != None:
        newNode = path_dict[node]
        node = newNode
        article_list.append(newNode)
    article_list.reverse()
    article_list.append(destination)
    return article_list
    
def process(s1, s2):
    valid1 = has_article(s1); valid2 = has_article(s2)
    if not(valid1):
        print("No such path exists. English Wikipedia does not have the" + 
              "following term: ", s1)
    if not(valid2):
        print("No such path exists. English Wikipedia does not have the" + 
              "following term: ", s2)
    if valid1 and valid2:
        article1 = find_actual_title(s1)
        article2 = find_actual_title(s2)
        if article1 == article2:
            print("\'" + s1 + "\'" + " and " + "\'" + s2 + "\'" +
                  " redirect to " + article1)
        else:
            print("PROCESSING", s1, "and", s2)
            resultant_path = bfs(article1, article2, True)
            print(resultant_path)

if is_csv_input:
    df_input = pd.read_csv("Sample Wikipedia inputs.csv")
    df_input['concat'] = df_input['Article1'] + ' ' + df_input['Article2']
    df_input['Answer No.'] = list(df_input.index)
    distinct_pairs = df_input.groupby('concat').agg({'Answer No.': np.min})
    all_article1 = list(df_input['Article1'])
    all_article2 = list(df_input['Article2'])
    idxs=list(distinct_pairs['Answer No.'])
    idxs.sort()
    for k in idxs:
        process(all_article1[k], all_article2[k])
else:
    term1 = input("Enter search term 1: ")
    term2 = input("Enter search term 2: ")
    process(term1, term2)