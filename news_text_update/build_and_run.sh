podman stop news-collector-gettext
podman rm news-collector-gettext
podman rmi localhost/news_text_update_text:latest
podman-compose up -d 
