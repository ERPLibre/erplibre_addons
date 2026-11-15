<?php // BEGIN PHP
$websitekey = basename(__DIR__);
// END PHP ?>
html { font-size: 100%; }
.bodywebsite h1 { color: <?php echo empty($website->maincolor) ? '#336699' : $website->maincolor; ?>; }
.bodywebsite .hero { background: url(medias/image/__WEBSITE_KEY__/logo.png); }
<?php // BEGIN PHP
$tmp = ob_get_contents(); ob_end_clean(); dolWebsiteOutput($tmp, "css");
// END PHP
