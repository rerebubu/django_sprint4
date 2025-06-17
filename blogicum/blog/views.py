from django.views.generic import (
    ListView,
    CreateView,
    UpdateView,
    DeleteView,
    DetailView,
)
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse
from django.db.models import Count, Prefetch
from django.core.paginator import Paginator

from .models import Category, Post, Comment, User
from .forms import PostForm, CommentForm, UserProfileForm
from .mixins import PostChangeMixin, CommentMixin

POST_COUNT = 10
PAGE_QUERY_PARAM = 'page'


# Функция для пагинации
def paginate_queryset(queryset, request, items_per_page=POST_COUNT, page_param=PAGE_QUERY_PARAM):
    paginator = Paginator(queryset, items_per_page)
    page_number = request.GET.get(page_param)
    page_obj = paginator.get_page(page_number)
    return page_obj


# Функция для вычисления количества комментариев
def annotate_comment_count(queryset):
    return queryset.annotate(comment_count=Count('comments'))


# Функция для фильтрации опубликованных постов
def filter_published_posts(queryset):
    return queryset.filter(is_published=True)


class PostListView(ListView):
    model = Post
    template_name = 'blog/index.html'
    paginate_by = POST_COUNT

    def get_queryset(self):
        # Применяем фильтрацию и аннотацию комментариями
        return annotate_comment_count(filter_published_posts(Post.published.select_related(
            'category', 'location', 'author'
        ))).order_by('-pub_date')  # Сортировка по дате публикации


class PostCreateView(LoginRequiredMixin, CreateView):
    model = Post
    template_name = 'blog/create.html'
    form_class = PostForm

    def form_valid(self, form):
        form.instance.author = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        return reverse(
            'blog:profile', kwargs={'username': self.request.user.username}
        )


class PostDetailView(DetailView):
    model = Post
    template_name = 'blog/detail.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        post = self.object  # Получаем пост
        user = self.request.user  # Получаем текущего пользователя

        # Проверка: если пост не опубликован и пользователь не является автором
        if not post.is_published and post.author != user:
            # Возвращаем ошибку 404 или редирект на другую страницу
            return redirect('blog:post_list')  # Например, редирект на список постов

        context['post'] = post
        context['form'] = CommentForm()
        context['comments'] = post.comments.select_related('post')
        return context


class PostUpdateView(PostChangeMixin, UpdateView):
    pass


class PostDeleteView(PostChangeMixin, DeleteView):
    def get_success_url(self):
        return reverse(
            'blog:profile', kwargs={'username': self.request.user.username}
        )


def category_posts(request, category_slug):
    template = 'blog/category.html'
    category = get_object_or_404(
        Category.objects.filter(
            is_published=True, slug=category_slug
        ).prefetch_related(
            Prefetch(
                'post_set',
                filter_published_posts(Post.published.select_related(
                    'category', 'location', 'author'
                )).annotate(comment_count=Count('comments')),
                'filtered_posts',
            )
        )
    )
    # Применяем пагинацию с фильтрованными постами
    page_obj = paginate_queryset(category.filtered_posts.order_by('-pub_date'), request)
    context = {'page_obj': page_obj, 'category': category}
    return render(request, template, context)


def profile(request, username):
    posts = (
        filter_published_posts(Post.published) if request.user.username != username else Post.objects
    )
    profile = get_object_or_404(
        User.objects.filter(username=username).prefetch_related(
            Prefetch(
                'post_set',
                posts.select_related('category', 'location', 'author')
                .order_by('-pub_date')  # Сортировка по дате публикации
                .annotate(comment_count=Count('comments')),
                'all_posts',
            )
        )
    )
    # Применяем пагинацию с фильтрованными постами
    page_obj = paginate_queryset(profile.all_posts.order_by('-pub_date'), request)
    context = {'profile': profile, 'page_obj': page_obj}
    return render(request, 'blog/profile.html', context)


@login_required
def edit_profile(request):
    if request.method == 'POST' and request.user.is_authenticated:
        form = UserProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            username = form.cleaned_data['username']
            return redirect('blog:profile', username=username)
    else:
        form = UserProfileForm(instance=request.user)
    context = {'form': form}
    return render(request, 'blog/user.html', context)


class CommentCreateView(LoginRequiredMixin, CreateView):
    post_object = None
    model = Comment
    form_class = CommentForm

    def dispatch(self, request, *args, **kwargs):
        self.post_object = get_object_or_404(Post, pk=kwargs['pk'])
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.author = self.request.user
        form.instance.post = self.post_object
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('blog:post_detail', kwargs={'pk': self.kwargs['pk']})


class CommentUpdateView(CommentMixin, UpdateView):
    pass


class CommentDeleteView(CommentMixin, DeleteView):
    pass