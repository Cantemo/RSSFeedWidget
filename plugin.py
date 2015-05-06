"""
This module contains example dashboard widgets.
"""
import logging

from django.utils.translation import ugettext as _

from portal.pluginbase.core import Plugin, implements
from portal.generic.dashboard_interfaces import IDashboardWidget
# Note: The following package must be imported at call-time in methods to prevent circular dependencies:
# from django import forms
# from django.core.cache import cache

log = logging.getLogger(__name__)


class RSSFeedWidget(Plugin):
    """
    A Dashboard widget for following an RSS feed.

    Warning: For simplicity this example widget does not use ETag or Last-Modified headers to reduce bandwidth.
    This means that for each update by each user the RSS feed is fully reloaded. With a frequent refresh interval
    the publisher may ban you from accessing their server, usually temporarily.
    """
    implements(IDashboardWidget)

    default_refresh = 30  # seconds
    default_feeds = (
        ('http://feeds.reuters.com/reuters/USVideoBreakingviews', "Reuters Breakingviews Video"),
        ('http://rss.cnn.com/rss/edition.rss', "CNN Top Stories"),
        ('http://rss.cnn.com/rss/cnn_latest.rss', "CNN Most Recent"),
        ('http://lorem-rss.herokuapp.com/feed?unit=second&interval=30', "Lorem Ipsum 30 sec"),
        ('http://lorem-rss.herokuapp.com/feed?unit=second&interval=5', "Lorem Ipsum 5 sec"),
        ('http://lorem-rss.herokuapp.com/feed?unit=second&interval=1', "Lorem Ipsum 1 sec"),
    )

    default_entry_count = 10

    _cache_timeout = 3600  # seconds

    def __init__(self):
        self.name = 'RSSFeedWidget'
        self.plugin_guid = '19F4BB8E-343D-43A6-A2A6-AC16D66CEA73'
        self.template_name = 'rss_feed_widget.html'
        self.configurable = True

    @staticmethod
    def get_list_title():
        return _("RSS feed")

    @staticmethod
    def _get_feed_cache_key(widget_id, session_key):
        """
        Get cache key for feed instance data.

        Previous entries are stored into cache to be able to animate new and old entries. If cache is disabled
        the widget will still work, but will not animate changes correctly.
        """
        return "RSSFeedWidget:%s:%s" % (widget_id, session_key)

    @staticmethod
    def get_render_data(render_data, settings, request):
        # Note: Django cache must be imported inside method:
        from django.core.cache import cache
        from time import time

        # Pass refresh interval to template
        try:
            render_data['refresh_interval'] = settings['refresh_interval']
        except KeyError:
            render_data['refresh_interval'] = RSSFeedWidget.default_refresh

        # Get feed_url from widget instance settings
        try:
            if settings['feed_url'] == 'custom':
                feed_url = settings['custom_url']
            else:
                feed_url = settings['feed_url']
        except KeyError:
            # settings is not initialized at all, use default feed
            feed_url = RSSFeedWidget.default_feeds[0][0]

        # Pass feed_url to template, potentially shown in error message
        render_data['feed_url'] = feed_url

        try:
            import feedparser
        except ImportError:
            render_data['error'] = (
                "Could not import \"feedparser\" library, install it with the following "
                "command and restart Portal:"
                "\n\n\n$ /opt/cantemo/python/bin/pip install feedparser"
            )
            return render_data

        # Read and parse the feed from the URL. Note: This always reads the full feed.
        start_time = time()
        parsed = feedparser.parse(feed_url)
        log.debug('RSSFeedWidget, feed loaded in %i ms, feed_url: %s', (time() - start_time) * 1000, feed_url)
        if parsed.bozo:
            log.error('Error parsing feed: %s', parsed.bozo_exception)
            render_data['error'] = repr(parsed.bozo_exception)
        else:
            # Current feed is passed to template
            render_data['feed'] = parsed.feed
            # Widget title is updated based on feed title
            render_data['title'] += ': ' + parsed.feed.title

            def entry_hash(e):
                # Entries are compared by the results of this function, so e.g. e.is_new does not affect comparison
                return e.published + e.title

            # Combine the new and previous entries into one list, marking which entries are new, and which should
            # be removed
            cache_key = RSSFeedWidget._get_feed_cache_key(render_data['id'], request.session.session_key)
            previous_entries = cache.get(cache_key, [])
            # Always limit entries to entry_count/default_entry_count
            try:
                entry_count = settings['entry_count']
            except KeyError:
                entry_count = RSSFeedWidget.default_entry_count
            parsed_entries = parsed.entries[:entry_count]
            cache.set(cache_key, parsed_entries, RSSFeedWidget._cache_timeout)

            previous_set = set(entry_hash(e) for e in previous_entries)
            parsed_set = set(entry_hash(e) for e in parsed_entries)

            render_entries = list(previous_entries)
            for e in render_entries:
                if not entry_hash(e) in parsed_set:
                    e.to_remove = True
                else:
                    e.to_remove = False
                e.is_new = False
            insert_to = 0
            for e in parsed_entries:
                if not entry_hash(e) in previous_set:
                    render_entries.insert(insert_to, e)
                    e.is_new = True
                    e.to_remove = False
                    insert_to += 1
            render_data['entries'] = render_entries

        return render_data

    @staticmethod
    def force_show_config(settings, request):
        # Show configuration if feed URL has not been set
        return 'feed_url' not in settings

    @staticmethod
    def get_config_form(settings, request):
        from django import forms

        class RSSFeedWidgetSettings(forms.Form):
            choices = RSSFeedWidget.default_feeds + (('custom', _("Custom RSS URL")),)
            feed_url = forms.ChoiceField(label=_("Feed to display"), choices=choices)
            custom_url = forms.URLField(label=_("Custom RSS URL"), required=False)
            refresh_interval = forms.IntegerField(label=_('Refresh interval (seconds):'),
                                                  initial=RSSFeedWidget.default_refresh, min_value=1)
            entry_count = forms.IntegerField(label=_('How many entries to show:'),
                                             initial=RSSFeedWidget.default_entry_count, min_value=1)

        return RSSFeedWidgetSettings

# Registers this class to global plugins
RSSFeedWidget()
