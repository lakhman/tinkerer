'''
    metadata
    ~~~~~~~~

    Blog metadata extension. The extension extracts and computes metadata
    associated with blog posts/pages and stores it in the environment.

    :copyright: Copyright 2011-2016 by Vlad Riscutia and contributors (see
    CONTRIBUTORS file)
    :license: FreeBSD, see LICENSE file
'''
import re
import datetime
import copy
from functools import partial
from sphinx.util.compat import Directive
from babel.core import Locale
from babel.dates import format_date

import tinkerer
from tinkerer.ext.uistr import UIStr
from tinkerer.utils import name_from_title


def initialize(app):
    '''
    Initializes metadata in environment.
    '''
    app.builder.env.blog_metadata = dict()
    app.builder.env.blog_warnings = []


class Metadata:
    '''
    Metadata associated with each post/page.
    '''
    num = 1

    def __init__(self):
        '''
        Initializes metadata with default values.
        '''
        self.is_post = False
        self.is_page = False
        self.is_article = False
        self.title = None
        self.link = None
        self.date = None
        self.formatted_date = None
        self.formatted_date_short = None
        self.body = None
        self.author = None
        self.excerpt = None
        self.filing = {"tags": [], "categories": []}
        self.comments, self.comment_count = False, False
        self.num = Metadata.num
        Metadata.num += 1


class CommentsDirective(Directive):
    '''
    Comments directive. The directive is not rendered by this extension, only
    added to the metadata, so plug-in comment handlers can be used.
    '''
    required_arguments = 0
    optional_arguments = 0
    has_content = False

    def run(self):
        '''
        Called when parsing the document.
        '''
        env = self.state.document.settings.env

        # mark page as having comments
        env.blog_metadata[env.docname].comments = True

        return []


class CreatedDirective(Directive):
    '''
    Created directive. `.. created:: Feb 6, 2016`
    This allows us to add a date for our `articles`
    Articles are our posts with nicer url's
    '''
    required_arguments = 0
    optional_arguments = 0
    has_content = True

    def run(self):
        return []


def get_metadata(app, docname, source):
    '''
    Extracts metadata from a document.
    '''

    # Ignore master and glossary pages
    if docname in ['master', 'glossary']:
        return

    env = app.builder.env
    language = app.config.language
    locale = Locale.parse(language) if language else Locale('en', 'US')
    format_ui_date = partial(
        format_date, format=UIStr.TIMESTAMP_FMT, locale=locale)
    format_short_ui_short = partial(
        format_date, format=UIStr.TIMESTAMP_FMT_SHORT, locale=locale)

    env.blog_metadata[docname] = Metadata()
    metadata = env.blog_metadata[docname]

    # Default author unless overridden
    metadata.author = app.env.config['author']

    # if it's an article
    if docname.startswith("blog/") or docname.startswith("cheatsheets/"):
        # Try to get parse our date directive from our source
        # date should be in format: `Feb 6, 2016`
        created = re.search("\.\.\screated::(.+)", source[0])

        # Add previous and next links manually after sorting
        # after doctree resolved? - somewhere else

        # If we have one, create a date from it
        if created:
            created_string = created.groups()[0].strip()
            try:
                date_object = datetime.datetime.strptime(created_string, '%b %d, %Y')
            except ValueError, error:
                try:
                    date_object = datetime.datetime.strptime(created_string, '%B %d, %Y')
                except ValueError, error:
                    date_object = datetime.datetime.today()
                    warnMsg = {
                        'type': 'Error',
                        'docname': docname,
                        'message': 'Error in parsing date for %s [%s], using today\'s date' % (docname, created_string)
                    }
                    env.blog_warnings.append(warnMsg)
                    app.warn("%s %s" % (warnMsg['type'], warnMsg['message']))

            metadata.is_article = True
            metadata.link = docname
            metadata.date = date_object

            # we format date here instead of inside template due to localization issues
            # and Python2 vs Python3 incompatibility
            metadata.formatted_date = format_ui_date(metadata.date)
            metadata.formatted_date_short = format_short_ui_short(metadata.date)

            return
        else:
            warnMsg = {
                'type': 'no_created_date',
                'docname': docname,
                'message': 'No date (created directive) was found for `%s`' % docname
            }
            env.blog_warnings.append(warnMsg)
            app.warn("%s %s" % (warnMsg['type'], warnMsg['message']))
            return

    # if it's a page
    if docname.startswith("pages/"):
        metadata.is_page = True
        return

    # posts are identified by ($YEAR)/($MONTH)/($DAY) paths
    match = re.match(r"\d{4}/\d{2}/\d{2}/", docname)

    # if not post return
    if not match:
        return

    metadata.is_post = True
    metadata.link = docname
    metadata.date = datetime.datetime.strptime(match.group(), "%Y/%m/%d/")

    # we format date here instead of inside template due to localization issues
    # and Python2 vs Python3 incompatibility
    metadata.formatted_date = format_ui_date(metadata.date)
    metadata.formatted_date_short = format_short_ui_short(metadata.date)


def process_metadata(app, env):
    '''
    Processes metadata after all sources are read - the function determines
    post and page ordering, stores doc titles and adds "Home" link to page
    list.
    '''
    # get ordered lists of posts and pages
    env.blog_posts, env.blog_pages = [], []
    relations = env.collect_relations()

    # start from root
    doc = tinkerer.master_doc

    # while not last doc
    while relations[doc][2]:
        doc = relations[doc][2]

        # if this is a post or a page (has metadata)
        if doc in env.blog_metadata:
            # set title
            env.blog_metadata[doc].title = env.titles[doc].astext()

            # ignore if parent is not master (eg. nested pages)
            if relations[doc][0] == tinkerer.master_doc:
                if env.blog_metadata[doc].is_post or env.blog_metadata[doc].is_article:
                    env.blog_posts.append(doc)
                elif env.blog_metadata[doc].is_page:
                    env.blog_pages.append(doc)

    # Get all docs not in the master doc (unrelated article items)
    unrelated_posts = [x for x in env.blog_metadata if x not in env.blog_posts]

    # Add our unrelated docs to our blog_posts for writing to aggregated pages
    for post in unrelated_posts:
        if post not in ['glossary', 'master']:
            metadata = env.blog_metadata[post]
            if metadata.date and metadata.date < datetime.datetime.now():
                # Add to our blog_posts list and mark it as an orphan
                # We do this so we don't have to insert everything in the master doc
                env.blog_posts.append(post)
                metadata.title = env.titles[post].astext()
                env.metadata[post]['orphan'] = True
            elif metadata.link:
                # We must have a link attribute to identify this as a post
                # Orphan "Draft" posts (posts with dates in the future), but log warning
                env.metadata[post]['orphan'] = True
                warnMsg = {
                    'type': 'draft',
                    'docname': metadata.link,
                    'message': '%s has a future date: %s' % (metadata.link, metadata.date.strftime('%d, %b %Y'))
                }
                env.blog_warnings.append(warnMsg)
                app.warn("%s %s" % (warnMsg['type'], warnMsg['message']))
            else:
                # We already warn about documents missing a date
                pass

    # Sort our blog_posts by date
    sortedList = []
    for doc in env.blog_posts:
        if env.blog_metadata[doc]:
            sortedList.append(copy.deepcopy(env.blog_metadata[doc]))
    sortedList.sort(key=lambda r: r.date, reverse=True)

    # Loop over our list and just get the key back - LOL - this could be better done
    sortedStringList = []
    for metadata in sortedList:
        sortedStringList.append(metadata.link)

    env.blog_posts = sortedStringList

    # navigation menu consists of first aggregated page and all user pages
    env.blog_page_list = [(page, env.titles[page].astext()) for page in env.blog_pages]

    # if using a custom landing page, that should be at the top of the nav menu
    if app.config.landing_page:
        env.blog_page_list.insert(1, ("page1", UIStr.HOME))
    # otherwise first aggregated page is at the top
    else:
        env.blog_page_list.insert(0, ("index", UIStr.HOME))


def add_metadata(app, pagename, context):
    '''
    Passes metadata to the templating engine.
    '''
    env = app.builder.env

    # page data
    context['website'] = app.config.website

    # blog tagline and pages
    context["tagline"] = app.config.tagline
    context["description"] = app.config.description
    context["pages"] = env.blog_page_list

    # set translation context variables
    context["text_recent_posts"] = UIStr.RECENT_POSTS
    context["text_posted_by"] = UIStr.POSTED_BY
    context["text_blog_archive"] = UIStr.BLOG_ARCHIVE
    context["text_filed_under"] = UIStr.FILED_UNDER
    context["text_tags"] = UIStr.TAGS
    context["text_tags_cloud"] = UIStr.TAGS_CLOUD
    context["text_categories"] = UIStr.CATEGORIES

    # recent posts
    context["recent"] = [(post, env.titles[post].astext()) for post
                         in env.blog_posts[:20]]
    # tags & categories
    tags, categories = [dict([(p, 0) for p in env.filing[c] if not
                        p.startswith('{{')]) for c in ["tags", "categories"]]
    taglinks = dict((t, name_from_title(t)) for t in tags)
    catlinks = dict([(c, name_from_title(c)) for c in categories])

    for post in env.blog_posts:
        p = env.blog_metadata[post]
        for tag in p.filing["tags"]:
            tags[tag[1]] += 1
        for cat in p.filing["categories"]:
            categories[cat[1]] += 1
    context["tags"] = tags
    context["taglinks"] = taglinks
    context["categories"] = categories
    context["catlinks"] = catlinks

    # if there is metadata for the page, it is not an auto-generated one
    if pagename in env.blog_metadata:
        context["metadata"] = env.blog_metadata[pagename]

        # if this is a post
        if pagename in env.blog_posts:
            # save body
            env.blog_metadata[pagename].body = context["body"]

            # no prev link if first post, no next link for last post
            if pagename == env.blog_posts[0]:
                context["prev"] = None
            if pagename == env.blog_posts[-1]:
                context["next"] = None

            # If it's a custom article, we add our own prev and next
            # above will be none
            if env.blog_metadata[pagename].is_article:
                if pagename == 'cheatsheets/sphinx/bootstrap-restructured-text-sphinx-directives':
                    pass

                pindex = env.blog_posts.index(pagename)
                prevIndex = pindex + 1
                nextIndex = pindex - 1

                if prevIndex < len(env.blog_posts):
                    context["prev"] = env.blog_metadata[env.blog_posts[prevIndex]]

                if nextIndex >= 0:
                    context["next"] = env.blog_metadata[env.blog_posts[nextIndex]]


        # if this is not documententation
        elif not (pagename.startswith("doc/") or pagename.startswith("docs/")):
            # no rellinks for non-posts/docs
            context["prev"], context["next"] = None, None

    # otherwise provide default metadata
    else:
        context["metadata"] = Metadata()
