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
    regex_prefixes = pipe.join(prefixes_complete)
    # remove disambiguation pages #
    cat_disambig_re = re.compile("^/wiki/Category:.*(D|d)isambiguation", re.I)
    needs_dab_re = re.compile("^/wiki/.*needing_disambiguation", re.I)
    cat_disambig = list(filter(lambda x: re.search(cat_disambig_re, x) != None
                               and re.search(needs_dab_re, x) == None,
                               hrefs))
    if(len(cat_disambig) > 0):
        return None
    # also exclude the Main Page, which changes daily and will lead to
    # unstable results
    non_article_regex = re.compile("^/wiki/((" + regex_prefixes +
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

def redirects(search_term):
    LEN_IKI = len("iki/")
    links_page_root = en_wiki_root[:-LEN_IKI]
    links_page_root += "/index.php?title=Special%3AWhat"
    links_page_root += "LinksHere&limit=500&hidetrans=1&hidelinks=1&target="
    links_page = requests.get(links_page_root + search_term)
    soup_from_page = BeautifulSoup(links_page.text, 'html.parser')
    a_tags=soup_from_page.find_all('a',href=True)
    hrefs=[elem['href'] for elem in a_tags]
    redirect_re = re.compile("&redirect=no") #re.compile("/w/index\.php?title=.+&redirect=no")
    redirect_links = list(filter(lambda x: re.search(redirect_re, x) != None,
                                 hrefs))
    LEN_PREFIX = len("/w/index.php?title=")
    LEN_REDIRECT = len("&redirect=no")
    redirects = [lk[LEN_PREFIX:-LEN_REDIRECT] for lk in redirect_links]
    return(set(redirects))

def extract_path_dict(three_in_one_dict):
    return({k: tup[0] for k, tup in three_in_one_dict.items()})

def analytics_print(analytics_dict):
    if(len(analytics_dict.keys()) <= 10):
        print(analytics_dict)
    else:
        analytics_idx = list(analytics_dict.keys())
        analytics_vals = list(analytics_dict.values())
        trimmed_dict = dict(zip(analytics_idx[-10:], analytics_vals[-10:]))
        print(trimmed_dict)
    return

# Reasoning adapted from Wikipedia's article on Breadth First Search
def bfs(origin_term, target_article, term_search=(False, None), verbose=False):
    TARGET_REDIRECTS = redirects(target_article)
    future_vertices = deque()
    visited = set(); count_wikilinks = 0
    three_in_one_dict = dict()
    # values: (parent article, distance from root, number of links on parent article, linked as)
    link_dict = dict()  # added for perf
    noentry_count = 0; disambig_count = 0; redirect_count = 0
    current_streak = 0; max_streak = 0
    # current_streak refers to red links, redirects, or disambiguations
    root = origin_term
    # key stores the parent node
    three_in_one_dict[root] = (None, 0, None) #, None)
    analytics_dict = dict()
    current_level = -1; max_dist = 0
    future_vertices.appendleft(root)
    levels = [1E4, 2.5E4, 5E4, 7.5E4, 1E5, 2E5, 2.5E5, 3E5, 4E5, 5E5, 7.5E5,
              1E6, 1.5E6, 2E6, 2.5E6]
    levels.sort()
#    pd.DataFrame({'levels': levels, 'visited'})
    attained_levels = set()
    while len(future_vertices) > 0:
        subtree_root = future_vertices.pop()
        actual_title = find_actual_title(subtree_root)
        if(actual_title == None):
            # linked from a page, but no article on EN Wikipedia yet for this term
            noentry_count += 1; current_streak += 1
            three_in_one_dict.pop(subtree_root)
            if verbose:
                print("Dead end: " + subtree_root)
            continue
        if(actual_title in visited):
            redirect_count += 1; current_streak += 1
#            if verbose:
#                print("Encountered redirect or term was previously visited:",
#                      subtree_root)
            continue
        if verbose:
            num_future = len(future_vertices)
            if((count_wikilinks > 0) and (count_wikilinks % 1000 == 0)):
                analytics_print(analytics_dict)
                print("==THIS ITERATION: ", str(count_wikilinks),
                      " V; ", str(num_future),
                      " TBS; ratio of ",
                      str(float(num_future) / float(count_wikilinks)), "; ",
                      str(noentry_count), " links with no article, ",
                      str(disambig_count), " disambiguation pages, ",
                      str(redirect_count), " redirects==",
                      sep="")
            if(current_level + 1 < len(levels)):
                next_level = levels[current_level + 1]
                if not(next_level in attained_levels) and len(
                        three_in_one_dict) >= next_level:
                    num_future = len(future_vertices)
                    analytics_print(analytics_dict)
                    print("Built up ", str(next_level), " entries in path",
                          " dictionary, having visited ", str(count_wikilinks),
                          " articles with ", str(num_future),
                          " to be explored (ratio of ",
                          str(num_future / count_wikilinks),
                          "); ",
                          str(noentry_count), " links with no article, ",
                          str(disambig_count), " disambiguation pages, ",
                          str(redirect_count), " redirects==",
                          sep="")
                    attained_levels.add(next_level)
                    current_level += 1
       
        current_dist = three_in_one_dict[subtree_root][1]
        if current_dist > max_dist:
            ### POTENTIAL SORTING FOR LV 2 and beyond ###
            if max_dist > 0:
                unique_visited = visited.intersection(three_in_one_dict.keys())
                list_unique_visited = list(unique_visited)
                list_unique_visited.sort()
                terms_prev_lv = list(filter(lambda k:
                    three_in_one_dict[k][1]==max_dist, unique_visited))
#                print(terms_prev_lv)
                num_links = [link_dict[k] for k in terms_prev_lv]
                link_tuples = list(zip(terms_prev_lv, num_links))
#                print(running_max_noncompliant(num_links))
#                print(running_min_noncompliant(num_links))
                link_tuples.sort(key=lambda tup: tup[1], reverse=True)
                if len(link_tuples) > 10:
                    print(link_tuples[:10])
                else:
                    print(link_tuples)
            max_dist = current_dist
            if verbose:
                num_future = len(future_vertices)
                analytics_print(analytics_dict)
                print("Reached depth ", current_dist, " with term ",
                      subtree_root, ", having visited ", str(count_wikilinks),
                      " articles and with ", str(num_future),
                      " to be explored (ratio of ",
                      str(num_future / count_wikilinks), ")",
                      sep="")
        if subtree_root == target_article: # can only happen with redirects
            if verbose:
                print("The search terms redirect to the same article")
            return construct_path(subtree_root, extract_path_dict(
                    three_in_one_dict))
            
        links = links_on_page(subtree_root)
        if(links == None): # Skipping: Disambiguation page, not an article
            disambig_count += 1; current_streak += 1
            if verbose:
                print("Disambiguation page removed: " + subtree_root)
            continue
        
        if current_streak > max_streak:
            max_streak = current_streak
            if verbose:
                print("Maximum streak extended to " + str(current_streak))
        current_streak = 0

        link_dict[subtree_root] = len(links)
        if actual_title != subtree_root:
            link_dict[actual_title] = len(links)
        link_names = set(links.keys())
        # there is a link on this page to the target
        if target_article in link_names:
            three_in_one_dict[target_article] = (subtree_root, current_dist+1,
                             len(links))
            if verbose:
                print("1st degree connection:", target_article, "-->",
                      links[target_article])
                if current_dist > 0:
                    print("Visited", str(count_wikilinks), "articles;",
                          "Added", str(len(three_in_one_dict)),
                          "entries to path dictionary")
            return construct_path(target_article, extract_path_dict(
                    three_in_one_dict))
        # O(1)
        redirects_in_links = link_names.intersection(TARGET_REDIRECTS)
        if len(redirects_in_links) > 0:
            print("Linked to redirect:")
            random_redirect = list(redirects_in_links)[0]
            three_in_one_dict[random_redirect] = (subtree_root,
                             current_dist+1, len(links))
            if current_dist > 0:
                print("Visited", str(count_wikilinks), "articles;", "Added",
                      str(len(three_in_one_dict)), "entries to path",
                      "dictionary")
            return construct_path(random_redirect,
                                  extract_path_dict(three_in_one_dict))
        link_children = set(links.keys())
        # no self links
        if term_search[0] and (re.match(term_search[1], subtree_root) != None
                      or re.match(term_search[1], actual_title) != None):
            print("^^Removing self reference^^")
        link_children.discard(subtree_root)
        # remove articles that have been previously visited
        if term_search[0] and (re.match(term_search[1], subtree_root) != None
                      or re.match(term_search[1], actual_title) != None):
            print("^^Removing previous visits^^")
        link_children.difference_update(visited)
        # remove articles that have already been marked for visitation
        if term_search[0] and (re.match(term_search[1], subtree_root) != None
                      or re.match(term_search[1], actual_title) != None):
            print("^^Removing future visits^^")
        link_children.difference_update(set(future_vertices))
        if term_search[0] and (re.match(term_search[1], subtree_root) != None
                      or re.match(term_search[1], actual_title) != None):
            print("^^Pruned. Adding children to dictionary and to-visit set.^^")
        for child in link_children:
            three_in_one_dict[child] = (subtree_root,
                             current_dist+1, len(links)) #, child)
            future_vertices.appendleft(child)
        num_new_links = len(link_children)
        num_article_links = len(links)
        if(re.match(term_search[1], subtree_root) != None
           or num_new_links >= 1000 or num_article_links >= 2000):
            print("^Processing " + subtree_root + " for link_children^")
            if num_new_links == 0:
                print("^^No new entries were added to dictionary,",
                      " though ", num_article_links, " unique links were",
                      " present.^^", sep="")
            else:
                print("^^Added ", num_new_links, " entries to dictionary,",
                      " with ", num_article_links, " unique links on the page",
                      " (", 100 * num_new_links / num_article_links,
                      "%).^^", sep="")
        count_wikilinks += 1
        visited.add(subtree_root)
        if actual_title != subtree_root:
            visited.add(actual_title)
        analytics_dict[count_wikilinks] = (len(future_vertices),
                      len(three_in_one_dict))

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
            resultant_path = bfs(article1,
                                 article2,
                                 term_search=(False,
#                                              re.compile("Alask|Isl|Arct",
#                                              re.compile("Shanghai|Putuo",
#                                              re.compile("^(Sich|Chengd)",
                                              re.compile("Chiba|Narita|Tokyo|Airport",
#                                              re.compile("(Maca(o|u))|(^Hong)|Guangdong",
                                                         re.I)),
                                              verbose=True)
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