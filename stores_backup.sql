--
-- PostgreSQL database dump
--

\restrict BqdIa3Zvrwh7Ci5BYMyWuQdOa7R8r7vnin9BlQAqTZ6XzVXP94cUQ814FaWeMR8

-- Dumped from database version 18.4
-- Dumped by pg_dump version 18.4

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: stores; Type: TABLE; Schema: public; Owner: pc_builder
--

CREATE TABLE public.stores (
    id integer NOT NULL,
    name character varying(50) NOT NULL,
    display_name character varying(100) NOT NULL,
    domain character varying NOT NULL,
    base_url character varying NOT NULL,
    currency character varying NOT NULL,
    currency_symbol character varying NOT NULL,
    search_config jsonb NOT NULL,
    product_config jsonb NOT NULL,
    active boolean NOT NULL,
    search_endpoint character varying CONSTRAINT stores_search_url_template_not_null NOT NULL
);


ALTER TABLE public.stores OWNER TO pc_builder;

--
-- Name: stores_id_seq; Type: SEQUENCE; Schema: public; Owner: pc_builder
--

CREATE SEQUENCE public.stores_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.stores_id_seq OWNER TO pc_builder;

--
-- Name: stores_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: pc_builder
--

ALTER SEQUENCE public.stores_id_seq OWNED BY public.stores.id;


--
-- Name: stores id; Type: DEFAULT; Schema: public; Owner: pc_builder
--

ALTER TABLE ONLY public.stores ALTER COLUMN id SET DEFAULT nextval('public.stores_id_seq'::regclass);


--
-- Data for Name: stores; Type: TABLE DATA; Schema: public; Owner: pc_builder
--

COPY public.stores (id, name, display_name, domain, base_url, currency, currency_symbol, search_config, product_config, active, search_endpoint) FROM stdin;
2	mdcomputers	MDComputers	mdcomputers.in	https://mdcomputers.in	INR	₹	{"selectors": {"mrp": "span.del", "image": "img", "price": "span.ins", "title": "h3.product-entities-title a", "product_card": "div.product-grid-item"}, "attributes": {"url": "href", "image": "src"}}	{}	t	https://mdcomputers.in/catalogsearch/result/?q={query}
4	pcstudio	PCStudio	pcstudio.in	https://www.pcstudio.in	INR	₹	{"selectors": {"mrp": "del .woocommerce-Price-amount", "image": "img", "price": "ins .woocommerce-Price-amount, .price .woocommerce-Price-amount", "title": "li.title a", "product_card": "ul.products > li.product"}, "attributes": {"url": "href", "image": "src"}}	{}	t	https://www.pcstudio.in/?s={query}&post_type=product
5	vedant	Vedant Computers	vedantcomputers.com	https://www.vedantcomputers.com	INR	₹	{"selectors": {"mrp": ".price-old", "image": ".product-img img", "price": ".price-new, .price", "title": ".name a", "product_card": ".main-products .product-layout"}, "attributes": {"url": "href", "image": "data-src"}}	{"mrp": ".price-old", "image": ".product-image img, .product-image-main img, .swiper-slide-active img", "price": ".price-new, .price", "title": "h1, .product-title h1", "description": "#tab-description, .tab-pane, .product-description"}	t	https://www.vedantcomputers.com/index.php?route=product/search&search={query}
6	primeabgb	PrimeABGB	primeabgb.com	https://www.primeabgb.com	INR	₹	{"selectors": {"mrp": "del .woocommerce-Price-amount", "image": ".product-image img", "price": ".price .woocommerce-Price-amount", "title": ".product-title", "product_card": ".product"}, "attributes": {"url": "href", "image": "src"}}	{"mrp": ".summary .price del .woocommerce-Price-amount", "image": ".woocommerce-product-gallery img", "price": ".summary .price ins .woocommerce-Price-amount, .summary .price > .woocommerce-Price-amount", "title": "h1.product_title", "description": "#tab-description, .woocommerce-Tabs-panel--description"}	t	https://www.primeabgb.com/?s={query}&post_type=product
\.


--
-- Name: stores_id_seq; Type: SEQUENCE SET; Schema: public; Owner: pc_builder
--

SELECT pg_catalog.setval('public.stores_id_seq', 6, true);


--
-- Name: stores stores_name_key; Type: CONSTRAINT; Schema: public; Owner: pc_builder
--

ALTER TABLE ONLY public.stores
    ADD CONSTRAINT stores_name_key UNIQUE (name);


--
-- Name: stores stores_pkey; Type: CONSTRAINT; Schema: public; Owner: pc_builder
--

ALTER TABLE ONLY public.stores
    ADD CONSTRAINT stores_pkey PRIMARY KEY (id);


--
-- PostgreSQL database dump complete
--

\unrestrict BqdIa3Zvrwh7Ci5BYMyWuQdOa7R8r7vnin9BlQAqTZ6XzVXP94cUQ814FaWeMR8

