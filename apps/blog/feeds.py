"""Feed RSS dos últimos posts (utilitário portado).

NOTA: este feed NÃO está ligado a nenhuma rota nesta fase — o blog opera como
gestão interna (somente staff), sem telas públicas. O arquivo é mantido pronto
para quando a fiação pública for decidida. Ao ligá-lo, será preciso também criar
a rota pública ``blog:home`` (usada em ``link``) e os detalhes de post.
"""
from django.contrib.syndication.views import Feed
from django.urls import reverse_lazy

from apps.blog.models import Post
from apps.blog.seo_utils import make_excerpt


class LatestPostsFeed(Feed):
    title = "Últimos posts"
    link = reverse_lazy("blog:home")
    description = "Acompanhe as publicações mais recentes do blog."

    def items(self):
        return Post.published.all()[:20]

    def item_title(self, item):
        return item.title

    def item_description(self, item):
        return item.excerpt or make_excerpt(item.content)

    def item_link(self, item):
        return item.get_absolute_url()

    def item_pubdate(self, item):
        return item.published_at
