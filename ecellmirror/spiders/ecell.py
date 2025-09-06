import scrapy
import os
from urllib.parse import urljoin, urlparse
from scrapy.spidermiddlewares.httperror import HttpError
from twisted.internet.error import DNSLookupError, TimeoutError

class EcellSpider(scrapy.Spider):
    name = "ecell"
    allowed_domains = ["ecellnmit.in", "www.ecellnmit.in"]  # Add www subdomain
    start_urls = ["https://www.ecellnmit.in/"]

    custom_settings = {
        'ROBOTSTXT_OBEY': False,
        'CONCURRENT_REQUESTS': 8,  # Reduced to prevent overload
        'DOWNLOAD_DELAY': 2,
        'COOKIES_ENABLED': False,
        'DOWNLOAD_TIMEOUT': 30,
        'RETRY_ENABLED': True,
        'RETRY_TIMES': 3,
        'HTTPERROR_ALLOWED_CODES': [404, 403],
    }

    def __init__(self, *args, **kwargs):
        super(EcellSpider, self).__init__(*args, **kwargs)
        # Create absolute path for downloads
        self.download_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "downloaded_site")
        os.makedirs(self.download_path, exist_ok=True)
        self.visited_urls = set()  # Track visited URLs

    def start_requests(self):
        for url in self.start_urls:
            yield scrapy.Request(
                url=url,
                callback=self.parse,
                errback=self.errback,
                dont_filter=True,
                meta={'dont_redirect': True}
            )

    def parse(self, response):
        try:
            if not response.body:
                self.logger.warning(f"Empty response from {response.url}")
                return

            content_type = response.headers.get("Content-Type", b"").decode("utf-8", errors='ignore').lower()
            
            # Skip if no content type or invalid URL
            if not content_type or not response.url:
                return

            # Handle redirects and different domains
            if not any(domain in response.url for domain in self.allowed_domains):
                return

            # ✅ Save HTML
            if "text/html" in content_type:
                self.save_file(response, "html")

                # Follow all links
                for href in response.css("a::attr(href), link::attr(href), script::attr(src), img::attr(src)").getall():
                    try:
                        # Clean and validate URL
                        url = response.urljoin(href)
                        parsed_url = urlparse(url)
                        if parsed_url.netloc in self.allowed_domains:
                            yield response.follow(url, self.parse, errback=self.errback)
                    except Exception as e:
                        self.logger.error(f"Error processing URL {href}: {str(e)}")

            # ✅ Save assets (images, css, js, etc.)
            else:
                try:
                    ext = content_type.split("/")[-1].split(";")[0].strip()  # e.g. image/png → png
                    if ext:
                        self.save_file(response, ext)
                except Exception as e:
                    self.logger.error(f"Error processing content type {content_type}: {str(e)}")

        except Exception as e:
            self.logger.error(f"Error processing response from {response.url}: {str(e)}")

    def save_file(self, response, ext):
        try:
            if not response.body:
                return

            # Clean URL path more thoroughly
            url_path = response.url.split('://', 1)[-1].split('?')[0]  # Remove query parameters
            file_path = os.path.join(self.download_path, url_path)

            # Validate file path
            if not file_path or len(file_path) > 255:  # Check path length
                self.logger.error(f"Invalid file path for {response.url}")
                return

            # If URL ends with / → save as index.html
            if file_path.endswith("/") or not os.path.splitext(file_path)[1]:
                if ext == "html":
                    file_path = os.path.join(file_path, "index.html")
                else:
                    file_path = file_path + f".{ext}"

            os.makedirs(os.path.dirname(file_path), exist_ok=True)

            self.logger.info(f"Saving {response.url} → {file_path}")
            with open(file_path, "wb") as f:
                f.write(response.body)
            self.logger.info(f"Saved file: {file_path}")
        except Exception as e:
            self.logger.error(f"Error saving file from {response.url}: {str(e)}")

    def errback(self, failure):
        if failure.check(HttpError):
            self.logger.error(f"HttpError on {failure.value.response.url}")
        elif failure.check(DNSLookupError):
            self.logger.error(f"DNSLookupError on {failure.request.url}")
        elif failure.check(TimeoutError):
            self.logger.error(f"TimeoutError on {failure.request.url}")
        else:
            self.logger.error(f"Other error on {failure.request.url}: {str(failure.value)}")
