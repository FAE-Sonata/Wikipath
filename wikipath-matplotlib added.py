# -*- coding: utf-8 -*-
import re
from collections import deque

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests
from bs4 import BeautifulSoup

is_csv_input = False
IKI = len("iki/")
PREFIX = len("/w/index.php?title=")
re_permlink = re.compile("Permanent link")
re_title = re.compile("title=")
re_oldid = re.compile("&oldid=")
wiki_regex = re.compile("^/wiki/")
cat_disambig_re = re.compile("^/wiki/Category:.*(D|d)isambiguation.*page(s)", re.I)
needs_dab_re = re.compile("^/wiki/.*needing_disambiguation", re.I)

""" exclude non-mainspace article pages on Wiki, i.e. those with the
following prefixes: """
prefixes = [
    "User",
    "Wikipedia",
    "File",
    "MediaWiki",
    "Template",
    "Help",
    "Category",
    "Portal",
    "Book",
    "Draft",
    "Education Program",
    "TimedText",
    "Module",
    "Gadget",
    "Gadget definition",
]
prefix_talk = [f"{s} talk" for s in prefixes]
prefixes_complete = prefixes + prefix_talk
prefixes_complete += ["Special", "Talk", "MOS"]
pipe = "|"
regex_prefixes = pipe.join(prefixes_complete)
non_article_regex = re.compile("^/wiki/((" + regex_prefixes + ":)|Main_Page)", re.I)
regraph_links_dict = None
while True:
    choice = input("Import search terms from a .CSV (Y/N)?: ")
    if re.match(re.compile("^([YN]|Yes|No)$", re.I), choice) is not None:
        if re.match(re.compile("^Y$", re.I), choice[0]) is not None:
            is_csv_input = True
        break

en_wiki_root = "https://en.wikipedia.org/wiki/"
depth_levels = []
NUM_TOP_LINKS = 10
top_link_tuples = None
SWITCH_TO_LOG = 10**1.5
ROLLING_SIZE = 100

RIGHT_BEGIN = 0.6
MIN_CLEARANCE_PRE_ROLLING = 0.15
MIN_CLEARANCE = 0.2
RESIZE_FACTOR = 1.3

""" run at beginning of search to determine whether either search term
has no article """


def has_article(search_term):
    if search_term.strip() == "":
        return False
    req_attempt = requests.get(en_wiki_root + search_term)
    return req_attempt.status_code != 404


def find_actual_title_helper(soup_from_page):
    link_titles = soup_from_page.find_all("a", title=True)
    title_text = [elem["title"] for elem in link_titles]
    # live articles should have ONE permanent link with revision ID
    has_oldid = [re.search(re_oldid, x["href"]) is not None for x in link_titles]
    idx_oldid = np.where(has_oldid)

    has_perm = [re.search(re_permlink, x) is not None for x in title_text]
    idx_perm = np.where(has_perm)
    if not (len(idx_oldid[0])):
        return None
    final_idx = (set(idx_oldid[0])).intersection(set(idx_perm[0]))
    assert len(final_idx)

    perm_link_suffix = link_titles[list(final_idx)[0]]["href"]
    char_idx_title = re.search(re_title, perm_link_suffix).end()
    char_idx_old_id = re.search(re_oldid, perm_link_suffix).start()
    return perm_link_suffix[char_idx_title:char_idx_old_id]


def find_actual_title(s):
    page = requests.get(en_wiki_root + s)
    # changed to LXML per https://beautiful-soup-4.readthedocs.io/en/latest/
    soup_from_page = BeautifulSoup(page.text, "html.parser")  #'lxml')
    res = find_actual_title_helper(soup_from_page)
    if res == None:
        print("THE FOLLOWING HAD NO PERMANENT REVISION LINK:", s)
    return res


# Given string "search_term", find ALL Article-namespace links on this page
# Includes links in article body AND in transcluded templates
def links_on_page(search_term):
    page = requests.get(en_wiki_root + search_term)
    soup_from_page = BeautifulSoup(page.text, "html.parser")  # 'lxml')
    a_tags = soup_from_page.find_all("a", href=True)
    hrefs = [elem["href"] for elem in a_tags]

    # remove disambiguation pages #
    cat_disambig = list(
        filter(
            lambda x: re.search(cat_disambig_re, x) is not None
            and re.search(needs_dab_re, x) == None,
            hrefs,
        )
    )
    # articles are not added to Disambiguation-labeled categories
    if len(cat_disambig) > 0:
        return None
    # also exclude the Main Page, which changes daily and will lead to
    # unstable results

    article_links = list(
        filter(
            lambda x: re.search(wiki_regex, x) is not None
            and re.search(non_article_regex, x) == None,
            hrefs,
        )
    )
    # "/wiki/" is 6 characters
    articles = [link[len("/wiki/") :] for link in article_links]
    unique_articles = set(articles)

    # remove reflexive links (particularly sectional links, e.g.
    # "Washington, D.C.#History" )
    this_term_actual_title = find_actual_title_helper(soup_from_page)
    if this_term_actual_title in unique_articles:
        unique_articles.remove(this_term_actual_title)
    res = dict(
        zip(
            list(unique_articles),
            ["Linked from " + search_term for s in unique_articles],
        )
    )
    return res


""" find terms that redirect to search_term, e.g.
"District of Columbia" to "Washington, D.C." """


def redirects(search_term):
    links_page_root = en_wiki_root[:-IKI]
    links_page_root += "/index.php?title=Special%3AWhatLinksHere"
    links_page_root += "&limit=500&hidetrans=1&hidelinks=1&target="
    links_page = requests.get(links_page_root + search_term)
    soup_from_page = BeautifulSoup(links_page.text, "html.parser")
    a_tags = soup_from_page.find_all("a", href=True)
    hrefs = [elem["href"] for elem in a_tags]
    redirect_re = re.compile("&redirect=no")
    redirect_links = list(
        filter(lambda x: re.search(redirect_re, x) is not None, hrefs)
    )
    REDIRECT = len("&redirect=no")
    redirects = [link[PREFIX:-REDIRECT] for link in redirect_links]
    return set(redirects)


def links_to(search_term):
    links_page_root = en_wiki_root[:-IKI]
    links_page_root += "/index.php?title=Special%3AWhatLinksHere/"
    links_page_root += search_term + "&namespace=0&hideredirs=1&limit=500"
    links_page = requests.get(links_page_root + search_term)
    soup_from_page = BeautifulSoup(links_page.text, "html.parser")
    a_tags = soup_from_page.find_all("a", href=True)
    # more than 500 links to page
    if "next 500" in [elem.get_text() for elem in a_tags]:
        return None
    hrefs = [elem["href"] for elem in a_tags]
    edit_re = re.compile("&action=edit")
    edit_links = list(filter(lambda x: re.search(edit_re, x) is not None, hrefs))
    AEDIT = len("&action=edit")
    links_to_target = set([link[PREFIX:-AEDIT] for link in edit_links])
    links_to_target.discard(search_term)
    return links_to_target


# condensed version of dictionary: only [key, child] duples returned
def extract_path_dict(three_in_one_dict):
    return {k: tup[0] for k, tup in three_in_one_dict.items()}


def calculate_diffs(running_links_dict):
    articles_with_additions = len(running_links_dict)
    links_added_total = [0] + list(
        map(lambda k: running_links_dict[k][0], range(1, articles_with_additions + 1))
    )
    # difference between consecutive elements of list
    links_added_diff = np.ediff1d(links_added_total)
    rolling_mean_added = None
    if len(links_added_diff) >= ROLLING_SIZE:
        lag = range(ROLLING_SIZE, len(links_added_diff) + 1)
        rolling_mean_added = [
            np.mean(links_added_diff[(k - ROLLING_SIZE) : k]) for k in lag
        ]
    return (links_added_diff, rolling_mean_added)


def calculate_mean_added(running_links_dict):
    articles_with_additions = len(running_links_dict)
    links_added_mean = list(
        map(
            lambda k: running_links_dict[k][0] / k,
            range(1, articles_with_additions + 1),
        )
    )
    return links_added_mean


def plot_links_added(running_links_dict, rescale=True):
    if len(running_links_dict) <= 1:
        return
    (instant, rolling) = calculate_diffs(running_links_dict)
    mean_added = calculate_mean_added(running_links_dict)

    fig, ax = plt.subplots(constrained_layout=True)
    x = list(range(1, len(running_links_dict) + 1))
    line_cumul = ax.plot(
        x, mean_added, color="tab:orange", linestyle="dashdot", label="Cumulative mean"
    )
    # resize left axis if legend is interfering with cumulative mean line
    left_upper = max(mean_added)
    right_max = max(mean_added[(int(RIGHT_BEGIN * len(mean_added))) :])
    exceeds_pre = len(mean_added) < ROLLING_SIZE and right_max > (
        1 - MIN_CLEARANCE_PRE_ROLLING
    ) * max(mean_added)
    exceeds = len(mean_added) >= ROLLING_SIZE and right_max > (1 - MIN_CLEARANCE) * max(
        mean_added
    )
    if exceeds_pre or exceeds:
        left_upper *= RESIZE_FACTOR
    ax.set_xlim([1, len(x)])
    ax.set_ylim([0, left_upper])

    large_first = max(mean_added) / mean_added[-1] > SWITCH_TO_LOG
    if large_first and rescale:
        ax.set_yscale("log")
        ax.set_ylim([1, max(mean_added)])

    for k in range(1, len(depth_levels)):
        plt.vlines(depth_levels[k], 0, max(instant), colors="red")

    ax.set_xlabel("Node#")
    ax.set_ylabel("Cumulative mean number of links added")

    ax2 = ax.twinx()
    # alpha fixes transparency so the 2 other lines are not overwhelmed
    line_instant = ax2.plot(
        x,
        instant,
        color="tab:blue",
        linestyle="dotted",
        alpha=0.25,
        label="Instantaneous added",
    )
    ax2.set_ylim([0, max(instant)])
    line_rolling = None
    if rolling is not None:
        line_rolling = ax2.plot(
            x[(ROLLING_SIZE - 1) :],
            rolling,
            color="tab:brown",
            label="Rolling %d average" % ROLLING_SIZE,
        )
    if line_rolling:
        combined_lines = line_cumul + line_instant + line_rolling
    else:
        combined_lines = line_cumul + line_instant
    if large_first and rescale:
        ax2.set_yscale("log")
        ax2.set_ylim([1, max(instant)])
    ax2.set_ylabel("Instantaneous number of links added")
    # https://stackoverflow.com/questions/5484922/secondary-axis-with-twinx-how-to-add-to-legend
    labels = [l.get_label() for l in combined_lines]
    ax.legend(combined_lines, labels, loc="upper right", shadow=True)
    plt.show()
    return (mean_added, rolling)


def plot_ratio(arr_ratios):
    if len(arr_ratios) <= 1:
        return
    cumulative_median = [
        np.median(arr_ratios[:k]) for k in range(1, len(arr_ratios) + 1)
    ]
    rolling_median = None
    if len(arr_ratios) >= ROLLING_SIZE:
        rolling_median = [
            np.median(arr_ratios[(k - ROLLING_SIZE) : k])
            for k in range(ROLLING_SIZE, len(arr_ratios) + 1)
        ]
    fig, ax = plt.subplots(constrained_layout=True)
    x = list(range(1, len(arr_ratios) + 1))
    ax.plot(x, cumulative_median, color="tab:green", label="Cumulative")
    if rolling_median is not None:
        ax.plot(
            range(ROLLING_SIZE, len(arr_ratios) + 1),
            rolling_median,
            color="tab:orange",
            linestyle="dashdot",
            label="Rolling %d median" % ROLLING_SIZE,
        )
    ax.set_xlim([1, len(x)])
    ax.set_ylim([0, 1])
    for k in range(1, len(depth_levels)):
        plt.vlines(depth_levels[k], 0, 1, colors="red")
    ax.set_xlabel("Node#")
    ax.set_ylabel("Median ratio |links added| : |links on article|")
    ax.legend(loc="upper right", shadow=True)
    plt.show()
    return (cumulative_median, rolling_median)


def bfs(origin_term, target_article, term_search=(False, None), verbose=False):
    # neither search term should be a disambiguation page; case of origin being
    # such a page handled below
    if links_on_page(target_article) == None:
        print("Target term is a disambiguation page")
        return None
    TARGET_REDIRECTS = redirects(target_article)
    target_section = re.compile("^" + target_article + "#.+", re.I)
    future_vertices = deque()
    visited = set()
    count_wikilinks = 0
    three_in_one_dict = dict()
    """ values in three_in_one_dict: (parent article, distance from root, number
    of links on parent article) """
    # miscellaneous statistics
    link_dict = dict()  # added for perf
    noentry_count = 0
    disambig_count = 0
    redirect_count = 0
    current_streak = 0
    max_streak = 0
    """ current_streak refers to red links (no article), redirects, or
    disambiguations """

    root = origin_term
    three_in_one_dict[root] = (None, 0, None)
    bfs_links_dict = dict()
    ratio_added = []
    current_level = -1
    max_dist = 0
    future_vertices.appendleft(root)
    # for progress updates during particularly large queries
    levels = [
        1e4,
        2.5e4,
        5e4,
        7.5e4,
        1e5,
        2e5,
        2.5e5,
        3e5,
        4e5,
        5e5,
        7.5e5,
        1e6,
        1.5e6,
        2e6,
        2.5e6,
    ]
    levels.sort()
    # tracking based on the levels above
    attained_levels = set()

    def final_plot():
        res_links = plot_links_added(bfs_links_dict)
        res_ratio = plot_ratio(ratio_added)
        if res_links is None or res_ratio is None:
            return
        (cumulative_mean, rolling_mean) = res_links
        (cumulative_median, rolling_median) = res_ratio

        def subplot(series_mean, series_median, x, cumulative):
            fig, ax = plt.subplots(constrained_layout=True)
            # x = list(range(1, len(series_mean)+1))
            line_cmean = ax.plot(
                x, series_mean, color="tab:orange", label="Mean links added"
            )
            ax.set_xlim([min(x), max(x)])
            ax.set_ylim([0, max(series_mean)])

            for k in range(1, len(depth_levels)):
                plt.vlines(depth_levels[k], 0, max(series_mean), colors="red")
            ax.set_xlabel("Node#")
            ax.set_ylabel("Mean number of links newly added")

            ax2 = ax.twinx()
            # alpha fixes transparency so the 2 other lines are not overwhelmed
            line_cmedian = ax2.plot(
                x, series_median, color="tab:green", label="Median ratio"
            )
            combined_lines = line_cmean + line_cmedian

            ax2.set_ylim([0, 1])
            ax2.set_ylabel("Median ratio |links added| : |links on article|")
            labels = [l.get_label() for l in combined_lines]
            ax.legend(combined_lines, labels, loc="upper right", shadow=True)
            # non-diagonal element of Numpy output
            series_corr = np.corrcoef(series_mean, series_median)[0][1]
            if cumulative:
                plt.title(f"Cumulative correlation: {series_corr:.4f}")
            else:
                plt.title(f"Rolling correlation: {series_corr:.4f}")
            plt.show()

        subplot(
            cumulative_mean,
            cumulative_median,
            list(range(1, len(cumulative_mean) + 1)),
            True,
        )
        if rolling_mean and rolling_median:
            subplot(
                rolling_mean,
                rolling_median,
                list(range(ROLLING_SIZE, len(cumulative_mean) + 1)),
                False,
            )

    def top_links():
        """analytics: sorting visited articles at previous level by
        number of links on page"""
        global top_link_tuples
        unique_visited = visited.intersection(three_in_one_dict.keys())
        # zip together dictionary {article: links}, reverse sort
        terms_prev_lv = list(
            filter(lambda k: three_in_one_dict[k][1] == max_dist, unique_visited)
        )
        num_links = [link_dict[k] for k in terms_prev_lv]
        link_tuples = list(zip(terms_prev_lv, num_links))
        link_tuples.sort(key=lambda tup: tup[1], reverse=True)
        if len(link_tuples) <= NUM_TOP_LINKS:
            top_link_tuples = link_tuples
            print(link_tuples)
        else:
            if top_link_tuples != link_tuples:
                prior_top = set()
                if top_link_tuples is not None:
                    prior_top = set([tup[0] for tup in top_link_tuples])
                new_top = set([tup[0] for tup in link_tuples[:NUM_TOP_LINKS]])
                removed = prior_top.difference(new_top)
                if len(removed):
                    removed_tuples = [
                        tup for tup in top_link_tuples if tup[0] in removed
                    ]
                    print("----------")
                    print("No longer in top %d: %s" % (NUM_TOP_LINKS, removed_tuples))
                added = new_top.difference(prior_top)
                if len(added):
                    added_tuples = [tup for tup in link_tuples if tup[0] in added]
                    print("++++++++++")
                    print("Added to top %d: %s" % (NUM_TOP_LINKS, added_tuples))
                top_link_tuples = link_tuples[:NUM_TOP_LINKS]

    while len(future_vertices) > 0:
        # remove next article off Queue (future_vertices) to examine #
        subtree_root = future_vertices.pop()
        actual_title = find_actual_title(subtree_root)
        if actual_title == None:
            # linked from a page, but no article on EN Wikipedia yet for this term
            noentry_count += 1
            current_streak += 1
            # not useful for any tracking dictionary #
            three_in_one_dict.pop(subtree_root)
            if verbose:
                print("Dead end: " + subtree_root)
            # next entry in Queue (future_vertices); nothing to be done
            continue
        # encountered redirect off Queue (future_vertices), nothing to be done
        if actual_title in visited:
            redirect_count += 1
            current_streak += 1
            continue
        if verbose:
            num_future = len(future_vertices)
            if (count_wikilinks > 0) and (count_wikilinks % 1000 == 0):
                top_links()
                plot_links_added(bfs_links_dict)
                one = "==THIS ITERATION: %d V; %d TBS; ratio of %f; %d " % (
                    count_wikilinks,
                    num_future,
                    num_future / count_wikilinks,
                    noentry_count,
                )
                two = "links with no article, %d disambiguation pages, %d" % (
                    disambig_count,
                    redirect_count,
                )
                print(one + two + " redirects==")
            # referring to certain milestones for |path_dict|, e.g. 100K, 1M
            if current_level + 1 < len(levels):
                next_level = levels[current_level + 1]
                if (
                    not (next_level in attained_levels)
                    and len(three_in_one_dict) >= next_level
                ):
                    top_links()
                    plot_links_added(bfs_links_dict)
                    one = "Built up %d entries in path dictionary, having" % (
                        next_level
                    )
                    two = " visited %d articles with %d to be explored " % (
                        count_wikilinks,
                        num_future,
                    )
                    tri = "(ratio of %f); %d links with no article, %d " % (
                        num_future / count_wikilinks,
                        noentry_count,
                        disambig_count,
                    )
                    four = "disambiguation pages, %d redirects==" % (redirect_count)
                    print(one + two + tri + four)
                    attained_levels.add(next_level)
                    current_level += 1

        current_dist = three_in_one_dict[subtree_root][1]
        # done exploring all vertices (articles) at current level
        if current_dist > max_dist:
            if max_dist > 0:
                top_links()
            max_dist = current_dist
            if verbose:
                num_future = len(future_vertices)
                depth_levels.append(len(bfs_links_dict))
                plot_links_added(bfs_links_dict)
                plot_ratio(ratio_added)
                print("==========")
                one = "Reached depth %d with term %s, having visited %d" % (
                    current_dist,
                    subtree_root,
                    count_wikilinks,
                )
                two = " articles and with %d to be explored (ratio of %f)" % (
                    num_future,
                    num_future / count_wikilinks,
                )
                print(one + two)
        if subtree_root == target_article:  # can only happen with redirects
            return (
                bfs_links_dict,
                construct_path(subtree_root, extract_path_dict(three_in_one_dict)),
            )

        links_this_page = links_on_page(subtree_root)
        if links_this_page == None:  # Skipping: Disambiguation page, not an article
            disambig_count += 1
            current_streak += 1
            if verbose:
                print("Disambiguation page removed: " + subtree_root)
            continue
        """ update max streak of red links (no article), redirects, or
        disambiguation pages, reset current streak to 0 since this term in
        Queue was not skipped """
        if current_streak > max_streak:
            max_streak = current_streak
            if verbose:
                plot_links_added(bfs_links_dict)
                print("Maximum streak extended to %d" % current_streak)
        current_streak = 0

        link_dict[subtree_root] = len(links_this_page)
        if actual_title != subtree_root:
            link_dict[actual_title] = len(links_this_page)
        link_names = set(links_this_page.keys())
        # there is a link on this page to the target
        if target_article in link_names:
            three_in_one_dict[target_article] = (
                subtree_root,
                current_dist + 1,
                len(links_this_page),
            )
            top_links()
            if verbose:
                final_plot()
                print(
                    "1st degree connection:",
                    target_article,
                    "<--",
                    links_this_page[target_article],
                )
                if current_dist > 0:
                    print("**********")
                    one = "Visited %d articles; Added %d entries to path " % (
                        count_wikilinks,
                        len(three_in_one_dict),
                    )
                    two = "dictionary, with %d still to be visited at " % (num_future)
                    tri = "conclusion (ratio of %f)" % (num_future / count_wikilinks)
                    print(one + two + tri)
            return (
                bfs_links_dict,
                construct_path(target_article, extract_path_dict(three_in_one_dict)),
            )

        # return if any links on this page are REDIRECTS to target article
        redirects_in_links = link_names.intersection(TARGET_REDIRECTS)
        if len(redirects_in_links) > 0:
            print("Linked to redirect:")
            random_redirect = list(redirects_in_links)[0]
            three_in_one_dict[random_redirect] = (
                subtree_root,
                current_dist + 1,
                len(links_this_page),
            )
            top_links()
            if current_dist > 0:
                print("**********")
                one = "Visited %d articles; Added %d entries to path " % (
                    count_wikilinks,
                    len(three_in_one_dict),
                )
                two = "dictionary, with %d still to be visited at " % (num_future)
                tri = "conclusion (ratio of %f)" % (num_future / count_wikilinks)
                print(one + two + tri)
            if verbose:
                final_plot()
            return (
                bfs_links_dict,
                construct_path(random_redirect, extract_path_dict(three_in_one_dict)),
            )

        # return if any links on this page are sectional links to target article
        matches_section = map(
            lambda x: re.match(target_section, x) is not None, link_names
        )
        if any(matches_section):
            print("Linked to section:")
            section_link = list(
                filter(lambda x: re.match(target_section, x) is not None, link_names)
            )[0]
            three_in_one_dict[section_link] = (
                subtree_root,
                current_dist + 1,
                len(links_this_page),
            )
            if verbose:
                final_plot()
            return (
                bfs_links_dict,
                construct_path(section_link, extract_path_dict(three_in_one_dict)),
            )

        # CLEAN LINKS #
        link_children = set(links_this_page.keys())
        # no self links
        link_children.discard(subtree_root)
        # remove articles that have been previously visited
        link_children.difference_update(visited)
        # remove articles that have already been marked for visitation
        link_children.difference_update(set(future_vertices))
        for child in link_children:
            """CONSTRUCT DICTIONARY with entry of valid child article linked:
            1. parent linked to (i.e. this page that was last popped off Queue)
            2. distance from 1st article, and
            3. number of links on page"""
            three_in_one_dict[child] = (
                subtree_root,
                current_dist + 1,
                len(links_this_page),
            )
            future_vertices.appendleft(child)
        num_new_links = len(link_children)
        num_article_links = len(links_this_page)
        """ NOT equal to cumulative |future_vertices|, since it excludes
        disambiguation pages and redirects """
        count_wikilinks += 1
        visited.add(subtree_root)
        if actual_title != subtree_root:
            visited.add(actual_title)
        """ number of fully processed articles: (|future queue|, |path dict|)
        the ratio |future queue| / count_wikilinks is an approximation of
        the mean number of links newly added to the "future queue" """
        bfs_links_dict[count_wikilinks] = (len(future_vertices), len(three_in_one_dict))
        ratio = num_new_links / num_article_links if num_article_links else 0
        ratio_added.append(ratio)
        # end of cycle in while loop


def construct_path(destination, path_dict):
    article_list = list()
    node = destination
    while path_dict[node] is not None:
        newNode = path_dict[node]
        node = newNode
        article_list.append(newNode)
    article_list.reverse()
    article_list.append(destination)
    return article_list


def process(s1, s2):
    valid1 = has_article(s1)
    valid2 = has_article(s2)
    if not (valid1):
        print(
            "No such path exists. English Wikipedia does not have the "
            + "following term: ",
            s1,
        )
    if not (valid2):
        print(
            "No such path exists. English Wikipedia does not have the "
            + "following term: ",
            s2,
        )
    if valid1 and valid2:
        article1 = find_actual_title(s1)
        article2 = find_actual_title(s2)
        if article1 == article2:
            print(
                "'" + s1 + "'" + " and " + "'" + s2 + "'" + " redirect to " + article1
            )
        else:
            print("PROCESSING '%s' and '%s'" % (s1, s2))
            query_res = bfs(article1, article2, verbose=True)
            if query_res is not None:
                (links_dict, resultant_path) = query_res
                print(resultant_path)
                return links_dict
            return None


if is_csv_input:
    df_input = pd.read_csv("Sample Wikipedia inputs.csv")
    df_input["concat"] = df_input["Article1"] + " " + df_input["Article2"]
    df_input["Answer No."] = list(df_input.index)
    distinct_pairs = df_input.groupby("concat").agg({"Answer No.": np.min})
    all_article1 = list(df_input["Article1"])
    all_article2 = list(df_input["Article2"])
    idxs = list(distinct_pairs["Answer No."])
    idxs.sort()
    for k in idxs:
        process(all_article1[k], all_article2[k])
else:
    term1 = input("Enter search term 1: ")
    term2 = input("Enter search term 2: ")
    regraph_links_dict = process(term1, term2)
