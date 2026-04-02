FROM nginx:alpine

# Copy the Nginx configuration file to the container
COPY ./container/nginx/default.conf /etc/nginx/conf.d/default.conf

# Create directories for SSL certificates
RUN mkdir -p /etc/nginx/ssl

# Generate self-signed SSL certificate (for testing purposes)
RUN apk add openssl && \
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout /etc/nginx/ssl/server.key \
    -out /etc/nginx/ssl/server.crt \
    -subj "/CN=localhost"
 \
# Expose ports 80 (HTTP) and 443 (HTTPS)
EXPOSE 80 443

