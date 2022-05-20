# Overview
A ["Wiki race"](https://www.inquirer.com/philly/living/20100721__Wikiracing__picking_up_speed_among_college_students.html) is where participants find _a_ shortest linkage path between two articles on English Wikipedia articles, e.g. `Washington, D.C.` and `Washington Metro` (which link each other). This script is intended to automatically mimic that, without the user directly interacting with Wikipedia source code or even scrolling thru any articles. Because any destination article will typically have dozens, even thousands, of other articles that link to it, shortest linkage paths are _not_ necessarily unique.

# Basic mechanics
In broad terms, the algorithm is an intricate application of [Breadth first search (BFS)](https://en.wikipedia.org/wiki/Breadth-first_search). To account for the high rate of edits ([1 billion cumulatively on the English edition as of 12 Jan 2021](https://www.vice.com/en/article/k7appn/the-english-language-wikipedia-just-had-its-billionth-edit)), "neighbors" of a node (visited article) are determined in real time; this is done by using BeautifulSoup to parse the article. The number of neighbors varies widely, from barely a dozen to over ten thousand.

## Some considerations
- Links may be found in a transcluded template on an article, and not anywhere in the body.
- Links may be redirects, e.g. `Washington, DC` instead of `Washington, D.C.`
- Links may point to sections, e.g. [`Money and the ethnic vote`](https://en.wikipedia.org/wiki/Money_and_the_ethnic_vote) to [a section in the 1995 Quebec referendum article](https://en.wikipedia.org/wiki/1995_Quebec_referendum#Immediate_responses)
- Disambiguation articles are not counted as they are practically not so different from Wikipedia space pages.

## Running the script
Any IDE that can run Python 3 and have the packages (`bs4`, `matplotlib.pyplot`, `numpy`, `requests`) installed. Inputting the origin and destination can be done either via the console or via a CSV file (`Sample Wikipedia inputs.csv`) that is located in the same directory as [the script](/wikipath-matplotlib%20added.py).

Command line compatibility is in the works.

# Visualization
Visualizations for certain metrics, such as mean load factor, are explained at the [presentation directory](/DVDC_Presentation/).