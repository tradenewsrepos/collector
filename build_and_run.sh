podman stop news-collector-getarticle
podman rm news-collector-getarticle
podman stop news-collector-gettext
podman rm news-collector-gettext
podman rmi localhost/news_text_update_text:latest
podman rmi localhost/news_download_article:latest 
podman-compose up -d 