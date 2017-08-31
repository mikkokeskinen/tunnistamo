(function($) {
  var breadcrumb = [{
    "id": null,
    "label": "Root"
  }];

  function updateBreadcrumb() {
    var breadcrumbEl = $('#breadcrumb');
    breadcrumbEl.empty();

    for (var i = 0; i < breadcrumb.length; i++) {
      var crumb = $('<li class="' + (i == breadcrumb.length - 1 ? "active" : "") + '" data-id="' + breadcrumb[i].id + '">' + breadcrumb[i].label + '</li>');
      breadcrumbEl.append(crumb);
    }
  }

  function remove_selected(id) {
    var selectedEl = $('#selected_concepts');
    var conceptSelect = $('#id_concepts_of_interest');
    var selectedIds = [];
    var parts = conceptSelect.val().split(',');

    for (var i = 0; i < parts.length; i++) {
      var numVal = parseInt(parts[i], 10);
      if (numVal && numVal !== id) {
        selectedIds.push(numVal);
      }
    }

    $(selectedEl).find('[data-id=' + id + ']').remove();
    conceptSelect.val(selectedIds.join(','));
  }

  function add_id(id, label) {
    var conceptSelect = $('#id_concepts_of_interest');
    var selectedIds = [];
    var parts = conceptSelect.val().split(',');

    for (var i = 0; i < parts.length; i++) {
      var numVal = parseInt(parts[i], 10);
      if (numVal) {
        selectedIds.push(numVal);
      }
    }

    if (selectedIds.indexOf(id) === -1 && parseInt(id, 10)) {
      selectedIds.push(id);

      var option = $('<li class="list-group-item" data-id="' + id + '">' + label + '</li>');
      option.on('click', function (e) {
        e.preventDefault();
        remove_selected(parseInt($(this).data('id'), 10));
      });
      $('#selected_concepts').append(option);

      conceptSelect.val(selectedIds.join(','));
    }
  }

  function get_and_view_concepts(el, ids, parentId) {
    $.ajax({
      url: CONCEPTS_URL,
      data: {
        'vocabulary_id': 11,
        'parent_id': parentId,
        'ids': ids
      }
    }).done(function (data) {

      data.sort(function (a, b) {
        if (a.label < b.label) {
          return -1;
        }
        if (a.label > b.label) {
          return 1;
        }

        return 0;
      });

      $(el).empty();

      if ($(el).attr('id') == 'concept_list') {
        var option = $('<li class="list-group-item" data-parent-id="' + parentId + '" >Back</li>');
        $(el).append(option);
        option.on('click', function (e) {
          e.preventDefault();
          if (breadcrumb.length == 1) {
            return;
          }

          breadcrumb.pop();
          var previous = breadcrumb[breadcrumb.length - 1];
          updateBreadcrumb();
          get_and_view_concepts(el, null, previous.id);
        });
      }

      for(i = 0; i < data.length; i++) {
        var option = $('<li class="list-group-item" data-id="' + data[i].id + '" data-member-id="' + data[i].member_id + '" data-label="' + data[i].label + '">' + data[i].label + '</li>');
        $(el).append(option);

        if ($(el).attr('id') == 'concept_list') {
          option.on('click', function (e) {
            e.preventDefault();
            add_id(parseInt($(this).data('id'), 10), $(this).data('label'));
          });

          var subLink = $('<a class="sub-link pull-right">+</a>').click(function (e) {
            e.preventDefault();
            e.stopPropagation();
            breadcrumb.push({
              'id': $(this).parent().data('member-id'),
              'label': $(this).parent().data('label')
            });
            updateBreadcrumb();
            get_and_view_concepts($(this).parents('ul'), null, $(this).parent().data('member-id'));
          });

          $(option).append(subLink);
        } else {
          option.on('click', function (e) {
            e.preventDefault();
            remove_selected(parseInt($(this).data('id'), 10));
          });
        }
      }
    });
  }

  $(document).ready(function () {
    $(document).ajaxSend(function (event, xhr, settings) {
      function getCookie(name) {
        var cookieValue = null;
        if (document.cookie && document.cookie != '') {
          var cookies = document.cookie.split(';');
          for (var i = 0; i < cookies.length; i++) {
            var cookie = jQuery.trim(cookies[i]);
            // Does this cookie string begin with the name we want?
            if (cookie.substring(0, name.length + 1) == (name + '=')) {
              cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
              break;
            }
          }
        }
        return cookieValue;
      }

      if (!(/^http:.*/.test(settings.url) || /^https:.*/.test(settings.url))) {
        // Only send the token to relative URLs i.e. locally.
        xhr.setRequestHeader("X-CSRFToken", getCookie('csrftoken'));
      }
    });

    var conceptSelect = $('#id_concepts_of_interest');
    conceptSelect.hide();

    var selectedIds = conceptSelect.val();
    var parentEl = conceptSelect.parent();
    var selectorWrapper = $('<div class="concept_selector_wrapper"></div>');
    var listEl = $('#concept_list');
    var selectedEl = $('#selected_concepts');

    get_and_view_concepts(selectedEl, selectedIds, null);
    get_and_view_concepts(listEl, null, null);
    updateBreadcrumb();

    $(selectorWrapper).insertAfter(parentEl);
  });
})(jQuery);
