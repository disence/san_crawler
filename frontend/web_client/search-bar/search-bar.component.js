angular.
	module('searchBar').
	component('searchBar', {
		templateUrl: 'search-bar/search-bar.template.html',
		controller: ['$scope', '$http',
			function SearchBarController($scope, $http) {
				var self = this;
				var api_url = 'http://127.0.0.1:8888';
				self.change = function () {
					if (self.querystr) {
						$http.get(api_url + '/list/' + self.querystr).then(function(response) {
							self.result = response.data.wwpn_list;
							self.details = {};
						});
					}
				};
				self.showDetails = function (wwpn) {
					self.selected = wwpn;
					$http.get(api_url + '/wwpn/' + wwpn).then(function(response) {
						self.details = response.data;
					});
				};
			}
		]
	});
