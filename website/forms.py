from django import forms
from django.contrib.auth.models import User
from .models import CustomerProfile, RentalPost, RentalVideo, Province, District, Ward, RechargeTransaction, LandlordReview
## Removed strong password validation per user request


class AccountProfileForm(forms.ModelForm):
    first_name = forms.CharField(max_length=150, required=False, label="Tên liên hệ")
    email = forms.EmailField(required=True, label="Email")
    phone = forms.CharField(max_length=15, required=False, label="Số điện thoại")

    class Meta:
        model = CustomerProfile
        fields = ["phone", "address"]

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        if user:
            self.fields["first_name"].initial = user.first_name or user.get_full_name()
            self.fields["email"].initial = user.email
            if hasattr(user, "customerprofile"):
                self.fields["phone"].initial = user.customerprofile.phone

    def apply_to_user(self, user: User):
        first_name = self.cleaned_data.get("first_name", "")
        user.first_name = first_name
        user.email = self.cleaned_data.get("email", user.email)
        user.save(update_fields=["first_name", "email"])
        profile: CustomerProfile = user.customerprofile
        # Đồng bộ display_name với first_name để hiển thị tên nhất quán
        profile.display_name = first_name
        profile.phone = self.cleaned_data.get("phone", profile.phone)
        profile.address = self.cleaned_data.get("address", profile.address)
        profile.save(update_fields=["display_name", "phone", "address"])


class RequestOTPForm(forms.Form):
    email = forms.EmailField(label="Email nhận OTP")
    purpose = forms.CharField(widget=forms.HiddenInput, initial="profile_update")


class VerifyOTPForm(forms.Form):
    code = forms.CharField(max_length=6, label="Mã OTP")
    purpose = forms.CharField(widget=forms.HiddenInput)


class ChangePasswordForm(forms.Form):
    current_password = forms.CharField(widget=forms.PasswordInput, label="Mật khẩu hiện tại")
    new_password = forms.CharField(widget=forms.PasswordInput, label="Mật khẩu mới")
    confirm_password = forms.CharField(widget=forms.PasswordInput, label="Xác nhận mật khẩu")

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("new_password") != cleaned.get("confirm_password"):
            raise forms.ValidationError("Mật khẩu xác nhận không khớp")
        # No strong password validation required
        return cleaned

class RegisterForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput)
    confirm_password = forms.CharField(widget=forms.PasswordInput)
    phone = forms.CharField(max_length=15, required=False)
    address = forms.CharField(widget=forms.Textarea, required=False)

    role = forms.ChoiceField(
        choices=CustomerProfile.ROLE_CHOICES,
        widget=forms.RadioSelect,
        label="Loại tài khoản"
    )

    class Meta:
        model = User
        fields = ['username', 'email', 'password', 'role']

    def clean_password(self):
        password = self.cleaned_data.get('password')

        # Kiểm tra độ dài tối thiểu 6 ký tự
        if len(password) < 6:
            raise forms.ValidationError("Mật khẩu phải có ít nhất 6 ký tự.")

        # Kiểm tra có cả chữ và số
        has_letter = any(c.isalpha() for c in password)
        has_digit = any(c.isdigit() for c in password)

        if not has_letter:
            raise forms.ValidationError("Mật khẩu phải chứa ít nhất một chữ cái.")

        if not has_digit:
            raise forms.ValidationError("Mật khẩu phải chứa ít nhất một chữ số.")

        return password

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        confirm_password = cleaned_data.get("confirm_password")
        if password != confirm_password:
            raise forms.ValidationError("Mật khẩu không khớp.")
        return cleaned_data

class RentalPostForm(forms.ModelForm):
    house_number = forms.CharField(label='Số nhà', required=False)
    phone_number = forms.CharField(max_length=15, required=False, label='Số điện thoại liên hệ')

    class Meta:
        model = RentalPost
        fields = ['title', 'description', 'price', 'area', 'province', 'district', 'ward', 'street', 'address', 'latitude', 'longitude', 'phone_number', 'category', 'features']
        labels = {
            'title': 'Tiêu đề',
            'description': 'Mô tả',
            'price': 'Giá',
            'area': 'Diện tích',
            'province': 'Tỉnh/Thành phố',
            'district': 'Quận/Huyện',
            'ward': 'Phường/Xã',
            'street': 'Đường/Phố',
            'address': 'Địa chỉ',
            'phone_number': 'Số điện thoại liên hệ',
            'category': 'Loại chuyên mục',
            'features': 'Đặc điểm nổi bật'
        }
        widgets = {
            'description': forms.Textarea(attrs={
                'rows': 3,
                'class': 'auto-resize-textarea',
                'placeholder': 'Mô tả chi tiết về phòng trọ...'
            }),
            'features': forms.CheckboxSelectMultiple,
            'address': forms.TextInput(attrs={'readonly': 'readonly'}),
            'street': forms.TextInput(attrs={
                'placeholder': 'Nhập tên đường để tìm kiếm...',
                'autocomplete': 'off'
            }),
            'latitude': forms.HiddenInput(),
            'longitude': forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Tối ưu: Chỉ load province, không load district/ward ngay
        # District và Ward sẽ được load qua AJAX khi user chọn
        self.fields['province'].queryset = Province.objects.only('id', 'name').all()

        # Nếu đang edit (có instance), load district và ward tương ứng
        if self.instance and self.instance.pk:
            if self.instance.province:
                self.fields['district'].queryset = District.objects.filter(
                    province=self.instance.province
                ).only('id', 'name')
            if self.instance.district:
                self.fields['ward'].queryset = Ward.objects.filter(
                    district=self.instance.district
                ).only('id', 'name')
        else:
            # Form mới: Để trống district và ward ban đầu
            self.fields['district'].queryset = District.objects.none()
            self.fields['ward'].queryset = Ward.objects.none()

        # Nếu có POST data, expand queryset để validation pass
        if 'district' in self.data:
            try:
                province_id = int(self.data.get('province'))
                self.fields['district'].queryset = District.objects.filter(
                    province_id=province_id
                ).only('id', 'name')
            except (ValueError, TypeError):
                pass

        if 'ward' in self.data:
            try:
                district_id = int(self.data.get('district'))
                self.fields['ward'].queryset = Ward.objects.filter(
                    district_id=district_id
                ).only('id', 'name')
            except (ValueError, TypeError):
                pass

class RentalVideoForm(forms.ModelForm):
    video = forms.FileField(required=False)

    class Meta:
        model = RentalVideo
        fields = ['video']


class RechargeForm(forms.ModelForm):
    """Form nạp tiền vào ví"""
    amount = forms.DecimalField(
        max_digits=15,
        decimal_places=0,
        min_value=10000,
        label="Số tiền nạp (VNĐ)",
        help_text="Số tiền tối thiểu: 10,000 VNĐ"
    )
    description = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3}),
        required=False,
        label="Ghi chú",
        help_text="Thông tin bổ sung về giao dịch"
    )

    class Meta:
        model = RechargeTransaction
        fields = ['amount', 'payment_method', 'description']
        labels = {
            'payment_method': 'Phương thức thanh toán',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['payment_method'].widget = forms.Select(choices=RechargeTransaction.PAYMENT_METHOD_CHOICES)
        self.fields['amount'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'Nhập số tiền muốn nạp'
        })
        self.fields['description'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'Ví dụ: Nạp tiền để đăng tin VIP...'
        })


class LandlordReviewForm(forms.ModelForm):
    rating = forms.ChoiceField(
        choices=[(i, f"{i} sao") for i in range(1, 6)],
        widget=forms.RadioSelect,
        label="Chấm điểm"
    )
    comment = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 4, 'placeholder': 'Chia sẻ trải nghiệm của bạn...'}),
        required=False,
        label="Nhận xét"
    )

    class Meta:
        model = LandlordReview
        fields = ['rating', 'comment']