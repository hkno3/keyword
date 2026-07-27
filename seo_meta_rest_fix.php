<?php
/**
 * SEO 메타 필드를 WordPress REST API에 노출
 * 이 코드를 WordPress 관리자 > Code Snippets 에 붙여넣기 하거나
 * functions.php 맨 아래에 추가하세요.
 */
add_action('init', function () {
    $meta_keys = [
        // Yoast SEO
        '_yoast_wpseo_metadesc',
        '_yoast_wpseo_focuskw',
        // Rank Math
        'rank_math_focus_keyword',
        'rank_math_description',
    ];

    foreach ($meta_keys as $key) {
        register_post_meta('post', $key, [
            'show_in_rest'  => true,
            'single'        => true,
            'type'          => 'string',
            'auth_callback' => function () {
                return current_user_can('edit_posts');
            },
        ]);
    }
});
