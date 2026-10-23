<?php // BEGIN PHP
$websitekey = basename(__DIR__);
// END PHP ?>
/* JS content (all pages) */
<?php // BEGIN PHP
$tmp = ob_get_contents(); ob_end_clean(); dolWebsiteOutput($tmp, "js");
// END PHP
