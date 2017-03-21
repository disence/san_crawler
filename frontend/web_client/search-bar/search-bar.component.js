angular.
	module('searchBar').
	component('searchBar', {
		templateUrl: 'search-bar/search-bar.template.html',
		controller: ['$scope', '$http',
			function SearchBarController($scope, $http) {
				var self = this;
				self.change = function () {
					if (self.querystr) {
						$http.get('http://remote-slave.humw.com:8888/list/' + self.querystr).then(function(response) {
							self.result = response.data.wwpn_list;
							self.details = {};
						});
					}
				};
				self.showDetails = function (wwpn) {
					self.selected = wwpn;
					$http.get('http://remote-slave.humw.com:8888/wwpn/' + wwpn).then(function(response) {
						self.details = response.data;
					});
				};
			}
		]
	});
