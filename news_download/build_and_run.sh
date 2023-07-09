podman stop news-collector-getarticle
podman rm news-collector-getarticle
podman rmi  localhost/news_download_article:latest
podman-compose up -d 
