<?php
/**
 * 키워드 조회수 트래커 — functions.php 하단에 추가
 * 로그인 상태 방문자는 카운트 제외
 */

// 포스트 조회수 증가 (로그인 유저 제외)
function kw_track_post_view() {
    if ( ! is_single() ) return;
    if ( is_user_logged_in() ) return;

    $post_id = get_the_ID();
    if ( ! $post_id ) return;

    $count = (int) get_post_meta( $post_id, '_post_views_count', true );
    update_post_meta( $post_id, '_post_views_count', $count + 1 );
}
add_action( 'wp_head', 'kw_track_post_view' );

// REST API에 조회수 필드 노출
add_action( 'rest_api_init', function () {
    register_rest_field( 'post', '_post_views_count', [
        'get_callback' => function ( $post ) {
            return (int) get_post_meta( $post['id'], '_post_views_count', true );
        },
        'schema' => [ 'type' => 'integer', 'description' => '포스트 조회수' ],
    ] );
} );
