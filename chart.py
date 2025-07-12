import os
import requests
from bs4 import BeautifulSoup

link = "https://www.grammaticalframework.org/lib/doc/absfuns.html"
local_filename = "absfuns.html"

if os.path.exists(local_filename):
    with open(local_filename, "r", encoding="utf-8") as f:
        html_content = f.read()
else:
    response = requests.get(link)
    html_content = response.text
    with open(local_filename, "w", encoding="utf-8") as f:
        f.write(html_content)

soup = BeautifulSoup(html_content, 'html.parser')

cats_old = {
    'all_clauses': [],
    'Cl': [],
    'RCl': [],
    'QCl': [],
    'AdvSlash': [],
    'ClSlash': [],
    'Utt': [],
    'NP': [],
    'VP': [],
    'AP': [],
    'Temp': [],
    'Pol': [],
}

cats = {
    'all_clauses': [],
}
dependencies = {}
for item in soup.find_all('tr'):
    cells = item.find_all('td')
    name = cells[0].text.strip()
    nodetype = cells[1].text.split()[-1]
    dependencies = cells[1].text.split()[:-1]
    for dep in dependencies:
        if dep == '->':
            dependencies.remove(dep)

    if nodetype not in cats:
        cats[nodetype] = []
    cats[nodetype].append(name)
    if nodetype in ['Cl', 'RCl', 'QCl', 'ClAdv', 'ClSlash', 'Utt', 'S']: # warning includes Utt and S
        cats['all_clauses'].append(name)
    elif any(dep in dependencies for dep in ['Cl', 'RCl', 'QCl', 'ClAdv', 'ClSlash', 'Utt', 'S', 'VP']):
        print(f"{name} has a clause dependency: {dependencies}")
        cats['all_clauses'].append(name)