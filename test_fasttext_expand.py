"""A simple test harness for FastTextLexicalExpander in expand.py"""
from expand import FastTextLexicalExpander


def test_en_demo():
    demo_words = ['running', 'dog', 'democracy', 'runnig']
    expander = FastTextLexicalExpander()
    expander.topic_words = set(demo_words)
    results = expander.expand('en', topn=10)
    print('Demo results for English:')
    for w in sorted(results):
        print('-', w)


if __name__ == '__main__':
    test_en_demo()
